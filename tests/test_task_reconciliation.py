"""Comprehensive tests for task reconciliation.

Tests for scripts/lib/task_reconciliation.py which handles synchronizing
expected task state with the actual Claude Code task list using POSITION-BASED
matching. Tasks are matched by numeric ID (1, 2, 3...), NOT by subject.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.lib.task_reconciliation import (
    TaskListContext,
    TaskListSource,
    CurrentTask,
    ConflictInfo,
    TaskOperation,
    ReconciliationResult,
    read_current_tasks,
    check_for_conflict,
    compute_operations,
    reconcile_tasks,
)


# =============================================================================
# TaskListContext Tests
# =============================================================================


class TestTaskListContextFromEnv:
    """Test TaskListContext.from_env() environment variable handling."""

    def test_neither_env_var_set(self):
        """No env vars -> task_list_id=None, source='none'."""
        with patch.dict("os.environ", {}, clear=True):
            ctx = TaskListContext.from_env()
            assert ctx.task_list_id is None
            assert ctx.source == TaskListSource.NONE
            assert ctx.is_user_specified is False

    def test_only_session_id_set(self):
        """CLAUDE_SESSION_ID only -> use it, source='session'."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "sess-123"}, clear=True):
            ctx = TaskListContext.from_env()
            assert ctx.task_list_id == "sess-123"
            assert ctx.source == TaskListSource.SESSION
            assert ctx.is_user_specified is False

    def test_only_user_env_set(self):
        """CLAUDE_CODE_TASK_LIST_ID only -> use it, source='user_env'."""
        with patch.dict("os.environ", {"CLAUDE_CODE_TASK_LIST_ID": "my-project"}, clear=True):
            ctx = TaskListContext.from_env()
            assert ctx.task_list_id == "my-project"
            assert ctx.source == TaskListSource.USER_ENV
            assert ctx.is_user_specified is True

    def test_both_env_vars_set_user_takes_priority(self):
        """Both set -> CLAUDE_CODE_TASK_LIST_ID wins."""
        with patch.dict("os.environ", {
            "CLAUDE_CODE_TASK_LIST_ID": "my-project",
            "CLAUDE_SESSION_ID": "sess-123",
        }, clear=True):
            ctx = TaskListContext.from_env()
            assert ctx.task_list_id == "my-project"
            assert ctx.source == TaskListSource.USER_ENV
            assert ctx.is_user_specified is True

    def test_empty_string_not_treated_as_set(self):
        """Empty string env vars behave like falsy values in Python."""
        # Note: os.environ.get("KEY") returns "" if KEY="" is set
        # In Python, empty string is falsy, so it falls through
        with patch.dict("os.environ", {"CLAUDE_CODE_TASK_LIST_ID": "", "CLAUDE_SESSION_ID": "sess-123"}, clear=True):
            ctx = TaskListContext.from_env()
            # Empty string is falsy, so it falls through to session
            assert ctx.task_list_id == "sess-123"
            assert ctx.source == TaskListSource.SESSION


class TestTaskListContextFromArgsAndEnv:
    """Test TaskListContext.from_args_and_env() with CLI args and env vars."""

    def test_context_session_id_takes_precedence(self):
        """--session-id (context) takes precedence over all env vars."""
        with patch.dict("os.environ", {
            "CLAUDE_CODE_TASK_LIST_ID": "user-task-list",
            "CLAUDE_SESSION_ID": "env-session-123",
        }, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id="context-session-456")
            assert ctx.task_list_id == "context-session-456"
            assert ctx.source == TaskListSource.CONTEXT
            assert ctx.is_user_specified is False

    def test_session_id_matched_true_when_same(self):
        """session_id_matched should be True when context and env have same value."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "same-session-id"}, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id="same-session-id")
            assert ctx.session_id_matched is True
            assert ctx.source == TaskListSource.CONTEXT

    def test_session_id_matched_false_when_different(self):
        """session_id_matched should be False when context and env differ (after /clear)."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "old-session-id"}, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id="new-session-id")
            assert ctx.session_id_matched is False
            assert ctx.task_list_id == "new-session-id"
            assert ctx.source == TaskListSource.CONTEXT

    def test_session_id_matched_none_when_only_context(self):
        """session_id_matched should be None when only context is present."""
        with patch.dict("os.environ", {}, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id="context-only")
            assert ctx.session_id_matched is None
            assert ctx.task_list_id == "context-only"

    def test_falls_back_to_user_env_when_no_context(self):
        """Falls back to CLAUDE_CODE_TASK_LIST_ID when no --session-id."""
        with patch.dict("os.environ", {
            "CLAUDE_CODE_TASK_LIST_ID": "user-task-list",
            "CLAUDE_SESSION_ID": "env-session",
        }, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id=None)
            assert ctx.task_list_id == "user-task-list"
            assert ctx.source == TaskListSource.USER_ENV
            assert ctx.is_user_specified is True

    def test_falls_back_to_session_env_when_no_context_or_user(self):
        """Falls back to CLAUDE_SESSION_ID when no --session-id or user env."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "env-session"}, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id=None)
            assert ctx.task_list_id == "env-session"
            assert ctx.source == TaskListSource.SESSION
            assert ctx.is_user_specified is False

    def test_none_when_nothing_available(self):
        """Returns NONE source when no session ID available anywhere."""
        with patch.dict("os.environ", {}, clear=True):
            ctx = TaskListContext.from_args_and_env(context_session_id=None)
            assert ctx.task_list_id is None
            assert ctx.source == TaskListSource.NONE

    def test_from_env_delegates_to_from_args_and_env(self):
        """from_env() should delegate to from_args_and_env(None)."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "sess-123"}, clear=True):
            ctx_env = TaskListContext.from_env()
            ctx_args = TaskListContext.from_args_and_env(context_session_id=None)
            assert ctx_env.task_list_id == ctx_args.task_list_id
            assert ctx_env.source == ctx_args.source


# =============================================================================
# read_current_tasks Tests - KEYED BY NUMERIC ID (POSITION)
# =============================================================================


class TestReadCurrentTasks:
    """Test read_current_tasks() file reading - keyed by numeric ID (position)."""

    def test_task_list_id_none_returns_empty(self):
        """None task_list_id -> empty dict."""
        result = read_current_tasks(None)
        assert result == {}

    def test_task_dir_does_not_exist(self, tmp_path, monkeypatch):
        """Non-existent directory -> empty dict."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = read_current_tasks("nonexistent-id")
        assert result == {}

    def test_empty_task_dir(self, tmp_path, monkeypatch):
        """Empty task directory -> empty dict."""
        task_dir = tmp_path / ".claude" / "tasks" / "test-id"
        task_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = read_current_tasks("test-id")
        assert result == {}

    def test_reads_valid_task_files_keyed_by_id(self, tmp_path, monkeypatch):
        """Valid JSON files are read and indexed by NUMERIC ID (position)."""
        task_dir = tmp_path / ".claude" / "tasks" / "test-id"
        task_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        task1 = {"id": "1", "subject": "Task One", "status": "pending", "description": "Desc 1"}
        task2 = {"id": "2", "subject": "Task Two", "status": "completed", "activeForm": "Working"}
        (task_dir / "1.json").write_text(json.dumps(task1))
        (task_dir / "2.json").write_text(json.dumps(task2))

        result = read_current_tasks("test-id")

        assert len(result) == 2
        # Keyed by numeric ID, not subject
        assert 1 in result
        assert 2 in result
        assert result[1].id == "1"
        assert result[1].subject == "Task One"
        assert result[1].status == "pending"
        assert result[2].id == "2"
        assert result[2].subject == "Task Two"
        assert result[2].status == "completed"

    def test_skips_invalid_json(self, tmp_path, monkeypatch):
        """Invalid JSON files are skipped without error."""
        task_dir = tmp_path / ".claude" / "tasks" / "test-id"
        task_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        (task_dir / "1.json").write_text('{"id": "1", "subject": "Valid", "status": "pending"}')
        (task_dir / "2.json").write_text('not json')

        result = read_current_tasks("test-id")
        assert len(result) == 1
        assert 1 in result

    def test_skips_missing_required_fields(self, tmp_path, monkeypatch):
        """Tasks missing id/subject/status are skipped."""
        task_dir = tmp_path / ".claude" / "tasks" / "test-id"
        task_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        (task_dir / "1.json").write_text('{"id": "1", "subject": "Complete", "status": "pending"}')
        (task_dir / "2.json").write_text('{"subject": "No ID", "status": "pending"}')
        (task_dir / "3.json").write_text('{"id": "3", "status": "pending"}')

        result = read_current_tasks("test-id")
        assert len(result) == 1
        assert 1 in result

    def test_handles_non_sequential_ids(self, tmp_path, monkeypatch):
        """Gaps in IDs are handled correctly."""
        task_dir = tmp_path / ".claude" / "tasks" / "test-id"
        task_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        (task_dir / "1.json").write_text('{"id": "1", "subject": "First", "status": "pending"}')
        (task_dir / "5.json").write_text('{"id": "5", "subject": "Fifth", "status": "completed"}')

        result = read_current_tasks("test-id")
        assert len(result) == 2
        assert 1 in result
        assert 5 in result
        assert 2 not in result  # Gap is preserved


# =============================================================================
# check_for_conflict Tests
# =============================================================================


class TestCheckForConflict:
    """Test check_for_conflict() conflict detection."""

    def test_session_based_with_tasks_no_conflict(self):
        """Session-based (is_user_specified=False) never conflicts."""
        ctx = TaskListContext(task_list_id="sess-123", source=TaskListSource.SESSION, is_user_specified=False)
        current_tasks = {1: CurrentTask(id="1", subject="Task A", status="pending", description="", active_form="")}

        result = check_for_conflict(ctx, current_tasks)
        assert result is None

    def test_user_specified_no_tasks_no_conflict(self):
        """User-specified but empty task list -> no conflict."""
        ctx = TaskListContext(task_list_id="my-proj", source=TaskListSource.USER_ENV, is_user_specified=True)

        result = check_for_conflict(ctx, {})
        assert result is None

    def test_user_specified_with_tasks_conflict(self):
        """User-specified + existing tasks -> conflict."""
        ctx = TaskListContext(task_list_id="my-proj", source=TaskListSource.USER_ENV, is_user_specified=True)
        current_tasks = {
            1: CurrentTask(id="1", subject="Task A", status="pending", description="", active_form=""),
            2: CurrentTask(id="2", subject="Task B", status="completed", description="", active_form=""),
            3: CurrentTask(id="3", subject="Task C", status="in_progress", description="", active_form=""),
            4: CurrentTask(id="4", subject="Task D", status="pending", description="", active_form=""),
        }

        result = check_for_conflict(ctx, current_tasks)

        assert result is not None
        assert result.task_list_id == "my-proj"
        assert result.existing_task_count == 4
        assert len(result.sample_subjects) == 3  # Max 3 samples

    def test_no_task_list_id_no_conflict(self):
        """No task_list_id -> no conflict check possible (is_user_specified is False)."""
        ctx = TaskListContext(task_list_id=None, source=TaskListSource.NONE, is_user_specified=False)
        current_tasks = {1: CurrentTask(id="1", subject="Task", status="pending", description="", active_form="")}

        result = check_for_conflict(ctx, current_tasks)
        assert result is None


# =============================================================================
# compute_operations Tests - Empty Inputs
# =============================================================================


class TestComputeOperationsEmpty:
    """Test compute_operations() with empty inputs."""

    def test_empty_expected_empty_current(self):
        """No expected, no current -> no operations."""
        ops = compute_operations([], {})
        assert ops == []

    def test_empty_expected_has_current(self):
        """No expected, has current -> all existing marked obsolete."""
        # If expected is empty, all existing tasks are beyond expected count (0)
        # and should be marked obsolete
        current = {
            1: CurrentTask(id="1", subject="Existing A", status="pending", description="", active_form=""),
            2: CurrentTask(id="2", subject="Existing B", status="in_progress", description="", active_form=""),
        }
        ops = compute_operations([], current)

        # All existing tasks should be marked obsolete
        assert len(ops) == 2
        assert all(op.params["subject"] == "[obsolete]" for op in ops)
        assert all(op.params["status"] == "completed" for op in ops)


# =============================================================================
# compute_operations Tests - Create Scenarios (no existing tasks)
# =============================================================================


class TestComputeOperationsCreate:
    """Test compute_operations() task creation scenarios (no existing tasks)."""

    def test_all_new_tasks_pending(self):
        """All expected tasks are new and pending -> TaskCreate only."""
        expected = [
            {"subject": "Task A", "status": "pending", "description": "Do A", "activeForm": "Doing A"},
            {"subject": "Task B", "status": "pending", "description": "Do B", "activeForm": "Doing B"},
        ]
        ops = compute_operations(expected, {})

        assert len(ops) == 2
        assert all(op.tool == "TaskCreate" for op in ops)
        assert all(op.then is None for op in ops)  # No follow-up for pending
        assert ops[0].params["subject"] == "Task A"
        assert ops[1].params["subject"] == "Task B"

    def test_new_task_completed_needs_followup(self):
        """New task with status=completed -> TaskCreate + then TaskUpdate."""
        expected = [
            {"subject": "Task A", "status": "completed", "description": "Done", "activeForm": ""},
        ]
        ops = compute_operations(expected, {})

        assert len(ops) == 1
        assert ops[0].tool == "TaskCreate"
        assert ops[0].then is not None
        assert ops[0].then["tool"] == "TaskUpdate"
        assert ops[0].then["params"]["status"] == "completed"

    def test_new_task_in_progress_needs_followup(self):
        """New task with status=in_progress -> TaskCreate + then TaskUpdate."""
        expected = [
            {"subject": "Task A", "status": "in_progress", "description": "Working", "activeForm": "Working"},
        ]
        ops = compute_operations(expected, {})

        assert len(ops) == 1
        assert ops[0].tool == "TaskCreate"
        assert ops[0].then is not None
        assert ops[0].then["params"]["status"] == "in_progress"


# =============================================================================
# compute_operations Tests - Transform Scenarios (position-based)
# =============================================================================


class TestComputeOperationsTransform:
    """Test compute_operations() position-based TRANSFORMATION scenarios."""

    def test_transform_single_task_different_subject(self):
        """Position 1 exists with different subject -> TaskUpdate to transform."""
        expected = [{"subject": "plugin_root=/path", "status": "completed", "description": "Context", "activeForm": ""}]
        current = {
            1: CurrentTask(id="1", subject="Old Subject", status="pending", description="Old desc", active_form="Old form"),
        }

        ops = compute_operations(expected, current)

        assert len(ops) == 1
        assert ops[0].tool == "TaskUpdate"
        assert ops[0].params["taskId"] == "1"
        assert ops[0].params["subject"] == "plugin_root=/path"
        assert ops[0].params["status"] == "completed"
        assert "Transform position 1" in ops[0].reason

    def test_transform_preserves_matching_fields(self):
        """Only update fields that differ."""
        expected = [{"subject": "Same Subject", "status": "completed", "description": "Same desc", "activeForm": ""}]
        current = {
            1: CurrentTask(id="1", subject="Same Subject", status="pending", description="Same desc", active_form=""),
        }

        ops = compute_operations(expected, current)

        assert len(ops) == 1
        assert ops[0].tool == "TaskUpdate"
        # Only status should be updated, not subject or description
        assert "subject" not in ops[0].params
        assert "description" not in ops[0].params
        assert ops[0].params["status"] == "completed"

    def test_no_op_when_all_fields_match(self):
        """Position exists with all matching fields -> no operation."""
        expected = [{"subject": "Task A", "status": "completed", "description": "Desc", "activeForm": "Form"}]
        current = {
            1: CurrentTask(id="1", subject="Task A", status="completed", description="Desc", active_form="Form"),
        }

        ops = compute_operations(expected, current)
        assert ops == []

    def test_status_transitions_via_transform(self):
        """Test status changes via position-based transform."""
        transitions = [
            ("pending", "in_progress"),
            ("pending", "completed"),
            ("in_progress", "pending"),
            ("in_progress", "completed"),
            ("completed", "pending"),
            ("completed", "in_progress"),
        ]
        for current_status, expected_status in transitions:
            expected = [{"subject": "Task", "status": expected_status, "description": "", "activeForm": ""}]
            current = {
                1: CurrentTask(id="1", subject="Task", status=current_status, description="", active_form=""),
            }

            ops = compute_operations(expected, current)

            assert len(ops) == 1, f"Failed for {current_status} -> {expected_status}"
            assert ops[0].params["status"] == expected_status


# =============================================================================
# compute_operations Tests - Mixed Transform + Create Scenarios
# =============================================================================


class TestComputeOperationsMixed:
    """Test compute_operations() with mixed transform + create scenarios."""

    def test_transform_existing_create_new(self):
        """Positions 1-2 exist (transform), positions 3-4 don't (create)."""
        expected = [
            {"subject": "plugin_root=/path", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "planning_dir=/dir", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "Step 3", "status": "in_progress", "description": "", "activeForm": "Working"},
            {"subject": "Step 4", "status": "pending", "description": "", "activeForm": ""},
        ]
        current = {
            1: CurrentTask(id="1", subject="Old Task 1", status="pending", description="", active_form=""),
            2: CurrentTask(id="2", subject="Old Task 2", status="pending", description="", active_form=""),
        }

        ops = compute_operations(expected, current)

        # Position 1: transform (subject change + status change)
        # Position 2: transform (subject change + status change)
        # Position 3: create + followup (in_progress)
        # Position 4: create (pending, no followup)

        update_ops = [op for op in ops if op.tool == "TaskUpdate" and "Transform" in op.reason]
        create_ops = [op for op in ops if op.tool == "TaskCreate"]

        assert len(update_ops) == 2
        assert len(create_ops) == 2
        assert create_ops[0].params["subject"] == "Step 3"
        assert create_ops[0].then is not None  # in_progress needs followup
        assert create_ops[1].then is None  # pending doesn't

    def test_real_world_deep_plan_scenario(self):
        """Simulate actual deep-plan: 11 existing tasks -> 21 expected tasks."""
        # Existing: 11 tasks with various subjects from previous workflow
        current = {
            i: CurrentTask(id=str(i), subject=f"Old Task {i}", status="pending", description="", active_form="")
            for i in range(1, 12)  # 1-11
        }

        # Expected: 21 deep-plan tasks (context + workflow steps)
        expected = [
            {"subject": "plugin_root=/path/to/plugin", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "planning_dir=/path/to/planning", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "initial_file=/path/to/spec.md", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "review_mode=external_llm", "status": "completed", "description": "", "activeForm": ""},
        ] + [
            {"subject": f"Step {i}", "status": "pending" if i > 6 else "completed", "description": "", "activeForm": ""}
            for i in range(6, 23)  # Steps 6-22
        ]

        ops = compute_operations(expected, current)

        # Positions 1-11: TaskUpdate to transform
        # Positions 12-21: TaskCreate
        update_ops = [op for op in ops if op.tool == "TaskUpdate"]
        create_ops = [op for op in ops if op.tool == "TaskCreate"]

        assert len(update_ops) == 11  # Transform all 11 existing
        assert len(create_ops) == 10  # Create 10 new (positions 12-21)

    def test_first_run_all_new(self):
        """First run: no current tasks, create all."""
        expected = [
            {"subject": "Research", "status": "in_progress", "description": "Research", "activeForm": "Researching"},
            {"subject": "Interview", "status": "pending", "description": "Interview", "activeForm": ""},
            {"subject": "Write Spec", "status": "pending", "description": "Spec", "activeForm": ""},
            {"subject": "Generate Plan", "status": "pending", "description": "Plan", "activeForm": ""},
        ]

        ops = compute_operations(expected, {})

        assert len(ops) == 4
        assert all(op.tool == "TaskCreate" for op in ops)
        # Only first one (in_progress) needs followup
        assert ops[0].then is not None
        assert all(op.then is None for op in ops[1:])

    def test_perfect_match_no_ops(self):
        """Current matches expected exactly by position -> no operations."""
        expected = [
            {"subject": "Step 1", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "Step 2", "status": "in_progress", "description": "", "activeForm": ""},
            {"subject": "Step 3", "status": "pending", "description": "", "activeForm": ""},
        ]
        current = {
            1: CurrentTask(id="1", subject="Step 1", status="completed", description="", active_form=""),
            2: CurrentTask(id="2", subject="Step 2", status="in_progress", description="", active_form=""),
            3: CurrentTask(id="3", subject="Step 3", status="pending", description="", active_form=""),
        }

        ops = compute_operations(expected, current)
        assert ops == []


# =============================================================================
# compute_operations Tests - Edge Cases
# =============================================================================


class TestComputeOperationsEdgeCases:
    """Test compute_operations() edge cases with position-based matching."""

    def test_gaps_in_existing_positions(self):
        """Existing tasks have gaps (1, 3 exist, 2 missing) -> handle gracefully."""
        expected = [
            {"subject": "Task 1", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "Task 2", "status": "pending", "description": "", "activeForm": ""},
            {"subject": "Task 3", "status": "pending", "description": "", "activeForm": ""},
        ]
        current = {
            1: CurrentTask(id="1", subject="Old 1", status="pending", description="", active_form=""),
            3: CurrentTask(id="3", subject="Old 3", status="pending", description="", active_form=""),
            # Position 2 doesn't exist
        }

        ops = compute_operations(expected, current)

        # Position 1: transform
        # Position 2: create (doesn't exist)
        # Position 3: transform
        update_ops = [op for op in ops if op.tool == "TaskUpdate"]
        create_ops = [op for op in ops if op.tool == "TaskCreate"]

        assert len(update_ops) == 2  # Positions 1 and 3
        assert len(create_ops) == 1  # Position 2
        assert create_ops[0].params["subject"] == "Task 2"

    def test_more_existing_than_expected(self):
        """More existing tasks than expected -> extra positions marked obsolete."""
        expected = [
            {"subject": "Task 1", "status": "completed", "description": "", "activeForm": ""},
        ]
        current = {
            1: CurrentTask(id="1", subject="Old 1", status="pending", description="", active_form=""),
            2: CurrentTask(id="2", subject="Old 2", status="pending", description="", active_form=""),
            3: CurrentTask(id="3", subject="Old 3", status="pending", description="", active_form=""),
        }

        ops = compute_operations(expected, current)

        # Position 1: transform to expected
        # Positions 2-3: mark obsolete
        assert len(ops) == 3

        # First op transforms position 1
        assert ops[0].params["taskId"] == "1"
        assert ops[0].params["subject"] == "Task 1"

        # Remaining ops mark positions 2-3 as obsolete
        obsolete_ops = [op for op in ops if op.params.get("subject") == "[obsolete]"]
        assert len(obsolete_ops) == 2
        assert all(op.params["status"] == "completed" for op in obsolete_ops)
        assert {op.params["taskId"] for op in obsolete_ops} == {"2", "3"}

    def test_subject_with_special_characters(self):
        """Subjects with special chars work correctly."""
        expected = [{"subject": "plugin_root=/path/to/plugin", "status": "completed", "description": "", "activeForm": ""}]
        current = {
            1: CurrentTask(id="1", subject="Old: (something) [different]", status="pending", description="", active_form=""),
        }

        ops = compute_operations(expected, current)

        assert len(ops) == 1
        assert ops[0].params["subject"] == "plugin_root=/path/to/plugin"

    def test_missing_optional_fields_in_expected(self):
        """Expected tasks missing description/activeForm should use defaults."""
        expected = [{"subject": "Task", "status": "pending"}]  # No description or activeForm

        ops = compute_operations(expected, {})

        assert ops[0].params["description"] == "Task"  # Falls back to subject
        assert ops[0].params["activeForm"] == ""

    def test_already_obsolete_tasks_not_re_updated(self):
        """Tasks already marked [obsolete] + completed are skipped."""
        expected = [
            {"subject": "Task 1", "status": "completed", "description": "", "activeForm": ""},
        ]
        current = {
            1: CurrentTask(id="1", subject="Old 1", status="pending", description="", active_form=""),
            2: CurrentTask(id="2", subject="[obsolete]", status="completed", description="", active_form=""),
            3: CurrentTask(id="3", subject="Old 3", status="pending", description="", active_form=""),
        }

        ops = compute_operations(expected, current)

        # Position 1: transform
        # Position 2: already obsolete, skip
        # Position 3: mark obsolete
        assert len(ops) == 2
        task_ids = {op.params["taskId"] for op in ops}
        assert task_ids == {"1", "3"}  # Position 2 skipped

    def test_obsolete_marking_with_gaps(self):
        """Extra positions with gaps are all marked obsolete."""
        expected = [
            {"subject": "Task 1", "status": "completed", "description": "", "activeForm": ""},
        ]
        current = {
            1: CurrentTask(id="1", subject="Old 1", status="pending", description="", active_form=""),
            3: CurrentTask(id="3", subject="Old 3", status="pending", description="", active_form=""),
            5: CurrentTask(id="5", subject="Old 5", status="pending", description="", active_form=""),
        }

        ops = compute_operations(expected, current)

        # Position 1: transform
        # Positions 3, 5: mark obsolete (they're beyond expected count of 1)
        assert len(ops) == 3
        obsolete_ops = [op for op in ops if op.params.get("subject") == "[obsolete]"]
        assert len(obsolete_ops) == 2
        assert {op.params["taskId"] for op in obsolete_ops} == {"3", "5"}


# =============================================================================
# reconcile_tasks Integration Tests
# =============================================================================


class TestReconcileTasksIntegration:
    """Integration tests for reconcile_tasks() with position-based matching."""

    def test_no_env_vars_still_computes_operations(self, tmp_path):
        """No env vars -> operations computed (all TaskCreate), no task_list_id."""
        expected = [
            {"subject": "Task 1", "status": "pending", "description": "Do 1", "activeForm": "Doing 1"},
        ]
        with patch.dict("os.environ", {}, clear=True):
            result = reconcile_tasks(tmp_path, expected)

        assert result.success is True
        assert result.task_list_id is None
        # Operations are still computed (all TaskCreate since no existing tasks)
        assert len(result.operations) == 1
        assert result.operations[0].tool == "TaskCreate"

    def test_session_based_new_session(self, tmp_path, monkeypatch):
        """New session with CLAUDE_SESSION_ID -> all creates, no conflict."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        expected = [
            {"subject": "Task 1", "status": "in_progress", "description": "Do 1", "activeForm": "Doing 1"},
            {"subject": "Task 2", "status": "pending", "description": "Do 2", "activeForm": ""},
        ]

        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "sess-123"}, clear=True):
            result = reconcile_tasks(tmp_path / "planning", expected)

        assert result.success is True
        assert result.task_list_id == "sess-123"
        assert result.task_list_source == TaskListSource.SESSION
        assert result.conflict is None
        assert len(result.operations) == 2
        assert all(op.tool == "TaskCreate" for op in result.operations)

    def test_user_specified_with_existing_tasks_conflict(self, tmp_path, monkeypatch):
        """User-specified task list with existing tasks -> conflict + transform operations."""
        task_dir = tmp_path / ".claude" / "tasks" / "my-project"
        task_dir.mkdir(parents=True)
        (task_dir / "1.json").write_text(json.dumps({
            "id": "1", "subject": "Existing Task", "status": "pending"
        }))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        expected = [{"subject": "New Task", "status": "pending", "description": "", "activeForm": ""}]

        with patch.dict("os.environ", {"CLAUDE_CODE_TASK_LIST_ID": "my-project"}, clear=True):
            result = reconcile_tasks(tmp_path / "planning", expected)

        assert result.success is True
        assert result.conflict is not None
        assert result.conflict.existing_task_count == 1
        # Position 1 exists -> TaskUpdate to transform
        assert len(result.operations) == 1
        assert result.operations[0].tool == "TaskUpdate"
        assert result.operations[0].params["subject"] == "New Task"

    def test_position_based_transform_and_create(self, tmp_path, monkeypatch):
        """Existing tasks are transformed, new positions are created."""
        task_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        task_dir.mkdir(parents=True)

        # Existing: 2 tasks with old subjects
        (task_dir / "1.json").write_text(json.dumps({
            "id": "1", "subject": "Old Task 1", "status": "pending", "description": "", "activeForm": ""
        }))
        (task_dir / "2.json").write_text(json.dumps({
            "id": "2", "subject": "Old Task 2", "status": "in_progress", "description": "", "activeForm": ""
        }))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Expected: 3 tasks with new subjects
        expected = [
            {"subject": "plugin_root=/path", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "planning_dir=/dir", "status": "completed", "description": "", "activeForm": ""},
            {"subject": "Step 6", "status": "in_progress", "description": "", "activeForm": "Working"},
        ]

        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "sess-123"}, clear=True):
            result = reconcile_tasks(tmp_path / "planning", expected)

        assert result.success is True
        assert result.conflict is None  # Session-based never conflicts

        ops = result.operations
        update_ops = [op for op in ops if op.tool == "TaskUpdate"]
        create_ops = [op for op in ops if op.tool == "TaskCreate"]

        # Positions 1-2: transform (TaskUpdate with new subject, status)
        assert len(update_ops) == 2
        assert update_ops[0].params["taskId"] == "1"
        assert update_ops[0].params["subject"] == "plugin_root=/path"
        assert update_ops[1].params["taskId"] == "2"
        assert update_ops[1].params["subject"] == "planning_dir=/dir"

        # Position 3: create (TaskCreate + then for in_progress)
        assert len(create_ops) == 1
        assert create_ops[0].params["subject"] == "Step 6"
        assert create_ops[0].then is not None

    def test_real_world_11_to_21_scenario(self, tmp_path, monkeypatch):
        """Real deep-plan scenario: 11 existing tasks -> 21 expected tasks."""
        task_dir = tmp_path / ".claude" / "tasks" / "sess-123"
        task_dir.mkdir(parents=True)

        # Create 11 existing tasks
        for i in range(1, 12):
            (task_dir / f"{i}.json").write_text(json.dumps({
                "id": str(i), "subject": f"Old Task {i}", "status": "pending", "description": "", "activeForm": ""
            }))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create 21 expected tasks
        expected = [
            {"subject": f"Expected Task {i}", "status": "completed" if i <= 10 else "pending", "description": "", "activeForm": ""}
            for i in range(1, 22)
        ]

        with patch.dict("os.environ", {"CLAUDE_SESSION_ID": "sess-123"}, clear=True):
            result = reconcile_tasks(tmp_path / "planning", expected)

        ops = result.operations
        update_ops = [op for op in ops if op.tool == "TaskUpdate"]
        create_ops = [op for op in ops if op.tool == "TaskCreate"]

        # Positions 1-11: transform via TaskUpdate
        assert len(update_ops) == 11
        # Positions 12-21: create via TaskCreate
        assert len(create_ops) == 10


# =============================================================================
# Dataclass Serialization Tests
# =============================================================================


class TestDataclassSerialization:
    """Test to_dict() methods on dataclasses."""

    def test_conflict_info_to_dict(self):
        """ConflictInfo serializes correctly."""
        info = ConflictInfo(
            task_list_id="my-project",
            existing_task_count=5,
            sample_subjects=["Task A", "Task B"],
        )
        result = info.to_dict()

        assert result == {
            "task_list_id": "my-project",
            "existing_task_count": 5,
            "sample_subjects": ["Task A", "Task B"],
        }

    def test_task_operation_to_dict_without_then(self):
        """TaskOperation without then serializes correctly."""
        op = TaskOperation(
            tool="TaskUpdate",
            params={"taskId": "1", "status": "completed"},
            reason="Update status",
        )
        result = op.to_dict()

        assert result == {
            "tool": "TaskUpdate",
            "params": {"taskId": "1", "status": "completed"},
            "reason": "Update status",
        }
        assert "then" not in result

    def test_task_operation_to_dict_with_then(self):
        """TaskOperation with then serializes correctly."""
        op = TaskOperation(
            tool="TaskCreate",
            params={"subject": "Task", "description": "Desc", "activeForm": ""},
            reason="New task",
            then={"tool": "TaskUpdate", "params": {"status": "in_progress"}},
        )
        result = op.to_dict()

        assert result["then"] == {"tool": "TaskUpdate", "params": {"status": "in_progress"}}

    def test_reconciliation_result_to_dict(self):
        """ReconciliationResult serializes correctly."""
        result = ReconciliationResult(
            success=True,
            task_list_id="sess-123",
            task_list_source=TaskListSource.SESSION,
            planning_dir="/path/to/planning",
            operations=[
                TaskOperation(tool="TaskCreate", params={"subject": "Task"}, reason="New"),
            ],
            conflict=None,
            message=None,
        )
        output = result.to_dict()

        assert output["success"] is True
        assert output["task_list_id"] == "sess-123"
        assert output["task_list_source"] == "session"
        assert output["planning_dir"] == "/path/to/planning"
        assert len(output["operations"]) == 1
        assert "conflict" not in output
        assert "message" not in output
