"""Tests for task storage module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.task_storage import (
    ConflictInfo,
    TaskToWrite,
    TaskWriteResult,
    build_dependency_graph,
    check_for_conflict,
    generate_section_tasks_to_write,
    get_tasks_dir,
    write_tasks,
)
from lib.tasks import TaskStatus


class TestGetTasksDir:
    """Tests for get_tasks_dir function."""

    def test_returns_path_in_home_claude_tasks(self):
        """Returns path under ~/.claude/tasks/."""
        result = get_tasks_dir("sess-abc123")
        assert result == Path.home() / ".claude" / "tasks" / "sess-abc123"

    def test_handles_user_specified_id(self):
        """Works with user-specified task list ID."""
        result = get_tasks_dir("my-shared-list")
        assert result == Path.home() / ".claude" / "tasks" / "my-shared-list"


class TestTaskToWrite:
    """Tests for TaskToWrite dataclass."""

    def test_to_file_dict_basic(self):
        """Converts to correct file format."""
        task = TaskToWrite(
            position=5,
            subject="Research Decision",
            status=TaskStatus.IN_PROGRESS,
            description="Decide on research approach",
            active_form="Deciding on research",
        )
        result = task.to_file_dict()
        assert result == {
            "id": "5",
            "subject": "Research Decision",
            "description": "Decide on research approach",
            "activeForm": "Deciding on research",
            "status": "in_progress",
            "blocks": [],
            "blockedBy": [],
        }

    def test_to_file_dict_with_dependencies(self):
        """Includes blocks and blockedBy in output."""
        task = TaskToWrite(
            position=6,
            subject="Execute Research",
            status=TaskStatus.PENDING,
            blocks=("7", "8"),
            blocked_by=("5",),
        )
        result = task.to_file_dict()
        assert result["blocks"] == ["7", "8"]
        assert result["blockedBy"] == ["5"]

    def test_position_as_string_id(self):
        """Position is converted to string for id field."""
        task = TaskToWrite(
            position=22,
            subject="Section task",
            status=TaskStatus.PENDING,
        )
        assert task.to_file_dict()["id"] == "22"


class TestTaskWriteResult:
    """Tests for TaskWriteResult dataclass."""

    def test_ok_factory(self, tmp_path: Path):
        """ok() creates successful result."""
        result = TaskWriteResult.ok("sess-123", 21, tmp_path)
        assert result.success is True
        assert result.task_list_id == "sess-123"
        assert result.tasks_written == 21
        assert result.tasks_dir == tmp_path
        assert result.error is None

    def test_err_factory(self):
        """err() creates failure result."""
        result = TaskWriteResult.err("sess-123", "Permission denied")
        assert result.success is False
        assert result.task_list_id == "sess-123"
        assert result.tasks_written == 0
        assert result.error == "Permission denied"


class TestConflictInfo:
    """Tests for ConflictInfo dataclass."""

    def test_to_dict(self):
        """to_dict() returns correct format."""
        info = ConflictInfo(
            task_list_id="my-list",
            existing_task_count=15,
            sample_subjects=["Task A", "Task B"],
        )
        result = info.to_dict()
        assert result == {
            "task_list_id": "my-list",
            "existing_task_count": 15,
            "sample_subjects": ["Task A", "Task B"],
        }


class TestCheckForConflict:
    """Tests for check_for_conflict function."""

    def test_session_based_no_conflict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Session-based task lists (is_user_specified=False) never conflict."""
        # Create existing tasks
        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(json.dumps({"subject": "Task 1"}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = check_for_conflict("sess-123", is_user_specified=False)
        assert result is None

    def test_user_specified_empty_no_conflict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """User-specified list with no existing tasks = no conflict."""
        tasks_dir = tmp_path / ".claude" / "tasks" / "my-list"
        tasks_dir.mkdir(parents=True)
        # Empty directory

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = check_for_conflict("my-list", is_user_specified=True)
        assert result is None

    def test_user_specified_with_tasks_returns_conflict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """User-specified list with existing tasks returns ConflictInfo."""
        tasks_dir = tmp_path / ".claude" / "tasks" / "my-list"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(json.dumps({"subject": "Old Task 1", "status": "pending"}))
        (tasks_dir / "2.json").write_text(json.dumps({"subject": "Old Task 2", "status": "completed"}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = check_for_conflict("my-list", is_user_specified=True)
        assert result is not None
        assert result.task_list_id == "my-list"
        assert result.existing_task_count == 2
        assert "Old Task 1" in result.sample_subjects
        assert "Old Task 2" in result.sample_subjects

    def test_conflict_includes_up_to_3_sample_subjects(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """ConflictInfo includes up to 3 sample subjects."""
        tasks_dir = tmp_path / ".claude" / "tasks" / "my-list"
        tasks_dir.mkdir(parents=True)
        for i in range(5):
            (tasks_dir / f"{i+1}.json").write_text(json.dumps({"subject": f"Task {i+1}"}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = check_for_conflict("my-list", is_user_specified=True)
        assert result is not None
        assert result.existing_task_count == 5
        assert len(result.sample_subjects) == 3

    def test_conflict_excludes_obsolete_from_samples(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Sample subjects exclude [obsolete] tasks."""
        tasks_dir = tmp_path / ".claude" / "tasks" / "my-list"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(json.dumps({"subject": "[obsolete]", "status": "completed"}))
        (tasks_dir / "2.json").write_text(json.dumps({"subject": "Valid Task", "status": "pending"}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = check_for_conflict("my-list", is_user_specified=True)
        assert result is not None
        assert result.existing_task_count == 2
        assert result.sample_subjects == ["Valid Task"]

    def test_nonexistent_directory_no_conflict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Nonexistent task directory = no conflict."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = check_for_conflict("nonexistent-list", is_user_specified=True)
        assert result is None


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""

    def test_empty_dependencies(self):
        """Tasks with no dependencies have empty blocks/blockedBy."""
        tasks = [
            TaskToWrite(position=1, subject="Task 1", status=TaskStatus.PENDING),
            TaskToWrite(position=2, subject="Task 2", status=TaskStatus.PENDING),
        ]
        semantic_deps: dict[str, list[str]] = {}
        semantic_to_pos = {"task-1": 1, "task-2": 2}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        assert result[1] == ([], [])
        assert result[2] == ([], [])

    def test_blocked_by_converted_to_positions(self):
        """Semantic blockedBy IDs converted to position strings."""
        tasks = [
            TaskToWrite(position=5, subject="Research Decision", status=TaskStatus.PENDING),
            TaskToWrite(position=6, subject="Execute Research", status=TaskStatus.PENDING),
        ]
        semantic_deps = {"execute-research": ["research-decision"]}
        semantic_to_pos = {"research-decision": 5, "execute-research": 6}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        # Position 6 is blocked by position 5
        assert result[6][1] == ["5"]

    def test_blocks_computed_from_blocked_by(self):
        """blocks array is inverse of blockedBy."""
        tasks = [
            TaskToWrite(position=5, subject="Research Decision", status=TaskStatus.PENDING),
            TaskToWrite(position=6, subject="Execute Research", status=TaskStatus.PENDING),
        ]
        semantic_deps = {"execute-research": ["research-decision"]}
        semantic_to_pos = {"research-decision": 5, "execute-research": 6}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        # Position 5 blocks position 6
        assert result[5][0] == ["6"]

    def test_context_tasks_blocked_by_output_summary(self):
        """Context tasks (1-4) are blocked by output-summary (21)."""
        tasks = [
            TaskToWrite(position=1, subject="plugin_root=/path", status=TaskStatus.PENDING),
            TaskToWrite(position=21, subject="Output Summary", status=TaskStatus.PENDING),
        ]
        semantic_deps = {"context-plugin-root": ["output-summary"]}
        semantic_to_pos = {"context-plugin-root": 1, "output-summary": 21}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        # Position 1 is blocked by 21
        assert result[1][1] == ["21"]
        # Position 21 blocks position 1
        assert result[21][0] == ["1"]

    def test_workflow_chain_dependencies(self):
        """Workflow tasks form proper dependency chain."""
        tasks = [
            TaskToWrite(position=5, subject="Task A", status=TaskStatus.PENDING),
            TaskToWrite(position=6, subject="Task B", status=TaskStatus.PENDING),
            TaskToWrite(position=7, subject="Task C", status=TaskStatus.PENDING),
        ]
        semantic_deps = {
            "task-a": [],
            "task-b": ["task-a"],
            "task-c": ["task-b"],
        }
        semantic_to_pos = {"task-a": 5, "task-b": 6, "task-c": 7}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        # 5 has no blockedBy, blocks 6
        assert result[5] == (["6"], [])
        # 6 is blocked by 5, blocks 7
        assert result[6] == (["7"], ["5"])
        # 7 is blocked by 6, blocks nothing
        assert result[7] == ([], ["6"])

    def test_unknown_semantic_ids_ignored(self):
        """Semantic IDs not in mapping are silently ignored."""
        tasks = [
            TaskToWrite(position=5, subject="Task A", status=TaskStatus.PENDING),
        ]
        # Dependency references unknown ID
        semantic_deps = {"task-a": ["unknown-task"]}
        semantic_to_pos = {"task-a": 5}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        # Unknown dependency is ignored
        assert result[5] == ([], [])

    def test_section_dependencies_included(self):
        """Section task dependencies are included in graph."""
        tasks = [
            TaskToWrite(position=20, subject="Write Sections", status=TaskStatus.PENDING),
            TaskToWrite(position=22, subject="Section 1", status=TaskStatus.PENDING),
            TaskToWrite(position=23, subject="Section 2", status=TaskStatus.PENDING),
        ]
        semantic_deps = {
            "write-sections": [],
            "section-22": ["write-sections"],
            "section-23": ["section-22"],
        }
        semantic_to_pos = {"write-sections": 20, "section-22": 22, "section-23": 23}

        result = build_dependency_graph(tasks, semantic_deps, semantic_to_pos)

        # 20 blocks 22
        assert "22" in result[20][0]
        # 22 is blocked by 20, blocks 23
        assert result[22][1] == ["20"]
        assert result[22][0] == ["23"]
        # 23 is blocked by 22
        assert result[23][1] == ["22"]


class TestWriteTasks:
    """Tests for write_tasks function."""

    def test_writes_single_task(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Single task writes to correct position file."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        task = TaskToWrite(
            position=1,
            subject="Test Task",
            status=TaskStatus.PENDING,
            description="A test task",
            active_form="Testing",
        )

        result = write_tasks("sess-123", [task])

        assert result.success is True
        assert result.tasks_written == 1

        task_file = tmp_path / ".claude" / "tasks" / "sess-123" / "1.json"
        assert task_file.exists()
        data = json.loads(task_file.read_text())
        assert data["id"] == "1"
        assert data["subject"] == "Test Task"
        assert data["status"] == "pending"

    def test_writes_multiple_tasks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Multiple tasks write in position order."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        tasks = [
            TaskToWrite(position=1, subject="Task 1", status=TaskStatus.COMPLETED),
            TaskToWrite(position=2, subject="Task 2", status=TaskStatus.IN_PROGRESS),
            TaskToWrite(position=3, subject="Task 3", status=TaskStatus.PENDING),
        ]

        result = write_tasks("sess-123", tasks)

        assert result.success is True
        assert result.tasks_written == 3

        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        for i, expected_status in enumerate(["completed", "in_progress", "pending"], start=1):
            data = json.loads((tasks_dir / f"{i}.json").read_text())
            assert data["id"] == str(i)
            assert data["status"] == expected_status

    def test_overwrites_existing_task(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Existing task at same position is overwritten."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create existing task
        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(json.dumps({"id": "1", "subject": "Old Task", "status": "pending"}))

        # Write new task at same position
        task = TaskToWrite(position=1, subject="New Task", status=TaskStatus.COMPLETED)
        result = write_tasks("sess-123", [task])

        assert result.success is True
        data = json.loads((tasks_dir / "1.json").read_text())
        assert data["subject"] == "New Task"
        assert data["status"] == "completed"

    def test_marks_extra_obsolete(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Extra existing tasks beyond written range marked obsolete."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create existing tasks at positions 1, 2, 3
        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        tasks_dir.mkdir(parents=True)
        for i in range(1, 4):
            (tasks_dir / f"{i}.json").write_text(
                json.dumps({"id": str(i), "subject": f"Task {i}", "status": "pending"})
            )

        # Write only position 1
        task = TaskToWrite(position=1, subject="New Task 1", status=TaskStatus.COMPLETED)
        result = write_tasks("sess-123", [task])

        assert result.success is True

        # Position 1 is new
        data1 = json.loads((tasks_dir / "1.json").read_text())
        assert data1["subject"] == "New Task 1"

        # Positions 2 and 3 marked obsolete
        for i in [2, 3]:
            data = json.loads((tasks_dir / f"{i}.json").read_text())
            assert data["subject"] == "[obsolete]"
            assert data["status"] == "completed"

    def test_skips_already_obsolete(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Already obsolete tasks not re-marked."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create already obsolete task
        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "2.json").write_text(
            json.dumps({
                "id": "2",
                "subject": "[obsolete]",
                "status": "completed",
                "blocks": ["3"],
                "blockedBy": ["1"],
            })
        )

        # Write only position 1
        task = TaskToWrite(position=1, subject="Task 1", status=TaskStatus.COMPLETED)
        result = write_tasks("sess-123", [task])

        assert result.success is True

        # Position 2 still has its blocks/blockedBy preserved
        data = json.loads((tasks_dir / "2.json").read_text())
        assert data["subject"] == "[obsolete]"
        assert data["blocks"] == ["3"]
        assert data["blockedBy"] == ["1"]

    def test_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Creates task directory if not exists."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        task = TaskToWrite(position=1, subject="Task 1", status=TaskStatus.PENDING)
        result = write_tasks("new-session", [task])

        assert result.success is True
        assert (tmp_path / ".claude" / "tasks" / "new-session").exists()

    def test_returns_error_on_missing_task_list_id(self):
        """Returns error result when task_list_id is empty."""
        result = write_tasks("", [])

        assert result.success is False
        assert result.error == "No task_list_id provided"

    def test_includes_blocks_and_blocked_by(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Task files include blocks and blockedBy arrays."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        task = TaskToWrite(
            position=5,
            subject="Task",
            status=TaskStatus.PENDING,
            blocks=("6", "7"),
            blocked_by=("4",),
        )
        result = write_tasks("sess-123", [task])

        assert result.success is True
        data = json.loads((tmp_path / ".claude" / "tasks" / "sess-123" / "5.json").read_text())
        assert data["blocks"] == ["6", "7"]
        assert data["blockedBy"] == ["4"]

    def test_dependency_graph_overrides_task_values(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Dependency graph overrides blocks/blockedBy on TaskToWrite."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        task = TaskToWrite(
            position=5,
            subject="Task",
            status=TaskStatus.PENDING,
            blocks=("wrong",),
            blocked_by=("wrong",),
        )
        dep_graph = {5: (["6"], ["4"])}

        result = write_tasks("sess-123", [task], dependency_graph=dep_graph)

        assert result.success is True
        data = json.loads((tmp_path / ".claude" / "tasks" / "sess-123" / "5.json").read_text())
        assert data["blocks"] == ["6"]
        assert data["blockedBy"] == ["4"]

    def test_preserves_blocks_when_marking_obsolete(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Marking obsolete preserves existing blocks/blockedBy fields."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create task with dependencies
        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "10.json").write_text(
            json.dumps({
                "id": "10",
                "subject": "Old Task",
                "status": "pending",
                "blocks": ["11"],
                "blockedBy": ["9"],
            })
        )

        # Write only position 1 to trigger obsolete marking
        task = TaskToWrite(position=1, subject="Task 1", status=TaskStatus.COMPLETED)
        write_tasks("sess-123", [task])

        # Position 10 is obsolete but keeps its blocks/blockedBy
        data = json.loads((tasks_dir / "10.json").read_text())
        assert data["subject"] == "[obsolete]"
        assert data["status"] == "completed"
        assert data["blocks"] == ["11"]
        assert data["blockedBy"] == ["9"]

    def test_mark_extra_obsolete_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Can disable marking extra tasks as obsolete."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create existing task
        tasks_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "2.json").write_text(
            json.dumps({"id": "2", "subject": "Keep Me", "status": "pending"})
        )

        # Write only position 1 with mark_extra_obsolete=False
        task = TaskToWrite(position=1, subject="Task 1", status=TaskStatus.COMPLETED)
        write_tasks("sess-123", [task], mark_extra_obsolete=False)

        # Position 2 is not marked obsolete
        data = json.loads((tasks_dir / "2.json").read_text())
        assert data["subject"] == "Keep Me"
        assert data["status"] == "pending"


class TestGenerateSectionTasksToWrite:
    """Tests for generate_section_tasks_to_write function."""

    def _create_index(self, sections_dir: Path, sections: list[str]) -> None:
        """Helper to create sections/index.md with SECTION_MANIFEST."""
        sections_dir.mkdir(parents=True, exist_ok=True)
        manifest = "\n".join(sections)
        content = f"""<!-- SECTION_MANIFEST
{manifest}
END_MANIFEST -->

# Implementation Plan Sections
"""
        (sections_dir / "index.md").write_text(content)

    def test_no_index_returns_empty(self, tmp_path: Path):
        """No sections/index.md returns empty list, empty deps, and count 0."""
        tasks, deps, count = generate_section_tasks_to_write(tmp_path)
        assert tasks == []
        assert deps == {}
        assert count == 0

    def test_invalid_index_returns_empty(self, tmp_path: Path):
        """Invalid SECTION_MANIFEST returns empty list, empty deps, and count 0."""
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir(parents=True)
        # Create index.md without proper manifest
        (sections_dir / "index.md").write_text("# No manifest here\n")

        tasks, deps, count = generate_section_tasks_to_write(tmp_path)
        assert tasks == []
        assert deps == {}
        assert count == 0

    def test_complete_returns_empty(self, tmp_path: Path):
        """All sections complete returns empty list, empty deps, and count 0."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro", "section-02-setup"])
        # Create both section files
        (sections_dir / "section-01-intro.md").write_text("# Intro")
        (sections_dir / "section-02-setup.md").write_text("# Setup")

        tasks, deps, count = generate_section_tasks_to_write(tmp_path)
        assert tasks == []
        assert deps == {}
        assert count == 0

    def test_positions_start_at_19(self, tmp_path: Path):
        """Batch task starts at position 19 (INSERT position), sections follow."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro", "section-02-setup"])

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        # 1 batch task + 2 section tasks = 3 total
        assert len(tasks) == 3
        assert count == 3
        # batch-1 at position 19
        assert tasks[0].position == 19
        assert tasks[0].subject == "Run batch 1 section subagents"
        # sections at 20, 21
        assert tasks[1].position == 20
        assert tasks[2].position == 21

    def test_custom_start_position(self, tmp_path: Path):
        """Can specify custom start position for batch task."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro"])

        tasks, _, count = generate_section_tasks_to_write(tmp_path, start_position=30)

        # 1 batch + 1 section = 2 tasks
        assert len(tasks) == 2
        assert count == 2
        assert tasks[0].position == 30  # batch-1
        assert tasks[1].position == 31  # section-01

    def test_batch_status_determination(self, tmp_path: Path):
        """Batch task is in_progress when it's the first incomplete batch."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro", "section-02-setup", "section-03-api"])

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        # 1 batch + 3 sections = 4 tasks
        assert len(tasks) == 4
        assert count == 4
        # Batch is in_progress (ready to work on)
        assert tasks[0].status == TaskStatus.IN_PROGRESS
        assert tasks[0].subject == "Run batch 1 section subagents"
        # All sections in the batch are also in_progress (parallel within batch)
        assert tasks[1].status == TaskStatus.IN_PROGRESS
        assert tasks[2].status == TaskStatus.IN_PROGRESS
        assert tasks[3].status == TaskStatus.IN_PROGRESS

    def test_completed_sections_have_completed_status(self, tmp_path: Path):
        """Written section files result in completed status, batch stays in_progress."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro", "section-02-setup", "section-03-api"])
        # Mark first section as complete
        (sections_dir / "section-01-intro.md").write_text("# Intro")

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        # 1 batch + 3 sections = 4 tasks
        assert len(tasks) == 4
        assert count == 4
        # Batch is still in_progress (not all sections complete)
        assert tasks[0].status == TaskStatus.IN_PROGRESS
        # First section is completed
        assert tasks[1].status == TaskStatus.COMPLETED
        # Remaining sections are in_progress (part of active batch)
        assert tasks[2].status == TaskStatus.IN_PROGRESS
        assert tasks[3].status == TaskStatus.IN_PROGRESS

    def test_batch_blocked_by_create_section_index(self, tmp_path: Path):
        """First batch (batch-1) is blocked by create-section-index."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro"])

        _, deps, _ = generate_section_tasks_to_write(tmp_path)

        assert deps["batch-1"] == ["create-section-index"]

    def test_sections_blocked_by_their_batch(self, tmp_path: Path):
        """Each section is blocked by its batch task."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro", "section-02-setup", "section-03-api"])

        _, deps, _ = generate_section_tasks_to_write(tmp_path)

        # batch-1 blocked by create-section-index
        assert deps["batch-1"] == ["create-section-index"]
        # All sections blocked by batch-1 (positions 20, 21, 22)
        assert deps["section-20"] == ["batch-1"]
        assert deps["section-21"] == ["batch-1"]
        assert deps["section-22"] == ["batch-1"]

    def test_task_subjects_include_filename(self, tmp_path: Path):
        """Section task subjects include section filename."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro"])

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        assert count == 2
        # First task is batch
        assert tasks[0].subject == "Run batch 1 section subagents"
        # Second task is section
        assert tasks[1].subject == "Write section-01-intro.md"
        assert tasks[1].description == "Write section file: section-01-intro.md"
        assert tasks[1].active_form == "Writing section-01-intro.md"

    def test_has_index_state_generates_tasks(self, tmp_path: Path):
        """has_index state (index exists but no sections written) generates batch + section tasks."""
        sections_dir = tmp_path / "sections"
        self._create_index(sections_dir, ["section-01-intro", "section-02-setup"])
        # No section files written

        tasks, deps, count = generate_section_tasks_to_write(tmp_path)

        # 1 batch + 2 sections = 3 tasks
        assert len(tasks) == 3
        assert count == 3
        # 1 batch dep + 2 section deps = 3 deps
        assert len(deps) == 3

    def test_partial_state_generates_remaining_tasks(self, tmp_path: Path):
        """partial state generates batch + section tasks (completed ones marked)."""
        sections_dir = tmp_path / "sections"
        self._create_index(
            sections_dir,
            ["section-01-intro", "section-02-setup", "section-03-api"],
        )
        # First section complete
        (sections_dir / "section-01-intro.md").write_text("# Intro")

        tasks, deps, count = generate_section_tasks_to_write(tmp_path)

        # 1 batch + 3 sections = 4 tasks
        assert len(tasks) == 4
        assert count == 4
        # Batch is in_progress (not all sections complete)
        assert tasks[0].status == TaskStatus.IN_PROGRESS
        # First section completed
        assert tasks[1].status == TaskStatus.COMPLETED
        # Remaining sections in_progress (part of active batch)
        assert tasks[2].status == TaskStatus.IN_PROGRESS
        assert tasks[3].status == TaskStatus.IN_PROGRESS

    def test_multiple_batches_structure(self, tmp_path: Path):
        """8 sections creates 2 batches with correct structure."""
        sections_dir = tmp_path / "sections"
        sections = [f"section-{i:02d}-s{i}" for i in range(1, 9)]  # 8 sections
        self._create_index(sections_dir, sections)

        tasks, deps, count = generate_section_tasks_to_write(tmp_path)

        # 2 batches + 8 sections = 10 tasks
        assert len(tasks) == 10
        assert count == 10

        # Batch 1 at position 19 (INSERT position)
        assert tasks[0].position == 19
        assert tasks[0].subject == "Run batch 1 section subagents"
        assert deps["batch-1"] == ["create-section-index"]

        # Sections 1-7 at positions 20-26, all blocked by batch-1
        for i in range(1, 8):
            assert tasks[i].position == 19 + i
            assert deps[f"section-{19 + i}"] == ["batch-1"]

        # Batch 2 at position 27 (19 + 8 = 27)
        assert tasks[8].position == 27
        assert tasks[8].subject == "Run batch 2 section subagents"
        assert deps["batch-2"] == ["batch-1"]

        # Section 8 at position 28, blocked by batch-2
        assert tasks[9].position == 28
        assert deps["section-28"] == ["batch-2"]

    def test_multiple_batches_status(self, tmp_path: Path):
        """First batch is in_progress, second batch is pending."""
        sections_dir = tmp_path / "sections"
        sections = [f"section-{i:02d}-s{i}" for i in range(1, 9)]  # 8 sections
        self._create_index(sections_dir, sections)

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        assert count == 10
        # Batch 1 is in_progress (ready to work on)
        assert tasks[0].status == TaskStatus.IN_PROGRESS
        # Sections in batch 1 are in_progress (parallel within batch)
        for i in range(1, 8):
            assert tasks[i].status == TaskStatus.IN_PROGRESS

        # Batch 2 is pending (waiting for batch 1)
        assert tasks[8].status == TaskStatus.PENDING
        # Section in batch 2 is pending
        assert tasks[9].status == TaskStatus.PENDING

    def test_batch_complete_when_all_sections_done(self, tmp_path: Path):
        """Batch is complete when all its sections are written."""
        sections_dir = tmp_path / "sections"
        sections = [f"section-{i:02d}-s{i}" for i in range(1, 9)]  # 8 sections
        self._create_index(sections_dir, sections)
        # Write all sections in batch 1
        for i in range(1, 8):
            (sections_dir / f"section-{i:02d}-s{i}.md").write_text(f"# Section {i}")

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        assert count == 10
        # Batch 1 is complete
        assert tasks[0].status == TaskStatus.COMPLETED
        # All batch 1 sections are complete
        for i in range(1, 8):
            assert tasks[i].status == TaskStatus.COMPLETED

        # Batch 2 is now in_progress (first incomplete batch)
        assert tasks[8].status == TaskStatus.IN_PROGRESS
        # Section in batch 2 is in_progress
        assert tasks[9].status == TaskStatus.IN_PROGRESS

    def test_batch_positions_formula(self, tmp_path: Path):
        """Batch positions follow formula: start + (batch-1) * (BATCH_SIZE + 1)."""
        sections_dir = tmp_path / "sections"
        # 15 sections = 3 batches (7 + 7 + 1)
        sections = [f"section-{i:02d}-s{i}" for i in range(1, 16)]
        self._create_index(sections_dir, sections)

        tasks, _, count = generate_section_tasks_to_write(tmp_path)

        # 3 batches + 15 sections = 18 tasks
        assert len(tasks) == 18
        assert count == 18

        # Batch 1 at position 19 (INSERT position)
        assert tasks[0].position == 19
        assert tasks[0].subject == "Run batch 1 section subagents"

        # Batch 2 at position 19 + 8 = 27
        assert tasks[8].position == 27
        assert tasks[8].subject == "Run batch 2 section subagents"

        # Batch 3 at position 27 + 8 = 35
        assert tasks[16].position == 35
        assert tasks[16].subject == "Run batch 3 section subagents"
