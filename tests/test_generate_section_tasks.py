"""Tests for generate-section-tasks.py script.

IMPORTANT: Direct Task File Writes
---------------------------------
The generate-section-tasks.py script writes task files directly to disk
at ~/.claude/tasks/<task_list_id>/ instead of returning operations for
Claude to execute.

Section tasks use POSITION-BASED matching:
- Section tasks start at position 22 (after 21 workflow tasks)
- Section[i] maps to position (22 + i): section[0] → 22, section[1] → 23, etc.
- Tasks are written directly as JSON files
- Dependencies create a chain: write-sections -> section-22 -> section-23 -> ...
"""

import json
import os
import subprocess
from pathlib import Path

import pytest


# =============================================================================
# Integration Tests: Script Execution
# =============================================================================


class TestGenerateSectionTasksScript:
    """Integration tests for generate-section-tasks.py script."""

    @pytest.fixture
    def script_path(self):
        """Return path to generate-section-tasks.py."""
        return Path(__file__).parent.parent / "scripts" / "checks" / "generate-section-tasks.py"

    @pytest.fixture
    def run_script(self, script_path):
        """Factory fixture to run generate-section-tasks.py."""
        def _run(planning_dir: Path, timeout=10, env_vars=None):
            """Run the script with given planning directory."""
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)

            result = subprocess.run(
                [
                    "uv", "run", str(script_path),
                    "--planning-dir", str(planning_dir),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result
        return _run

    @pytest.fixture
    def sample_index_content(self):
        """Sample index.md content with SECTION_MANIFEST block."""
        return """<!-- SECTION_MANIFEST
section-01-setup
section-02-api
section-03-database
section-04-integration
END_MANIFEST -->

# Implementation Sections Index

## Sections
"""

    def test_fresh_state_returns_error(self, run_script, tmp_path):
        """Should return error when no sections directory exists."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()

        result = run_script(planning_dir)

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "index.md" in output["error"]
        assert output["state"] == "fresh"
        assert output["tasks_written"] == 0

    def test_invalid_index_returns_error(self, run_script, tmp_path):
        """Should return error when index.md has invalid SECTION_MANIFEST."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        # Index without SECTION_MANIFEST block
        (sections_dir / "index.md").write_text("# Index\n\nNo manifest here")

        result = run_script(planning_dir)

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert output["state"] == "invalid_index"
        assert "SECTION_MANIFEST" in output["error"]
        assert output["tasks_written"] == 0

    def test_complete_state_returns_zero_tasks_written(self, run_script, tmp_path, sample_index_content):
        """Should return zero tasks_written when all sections are complete."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)
        (sections_dir / "section-01-setup.md").write_text("# Section 1")
        (sections_dir / "section-02-api.md").write_text("# Section 2")
        (sections_dir / "section-03-database.md").write_text("# Section 3")
        (sections_dir / "section-04-integration.md").write_text("# Section 4")

        result = run_script(planning_dir)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["state"] == "complete"
        assert output["stats"]["total"] == 4
        assert output["stats"]["completed"] == 4
        assert output["stats"]["missing"] == 0
        assert output["tasks_written"] == 0

    def test_no_session_id_returns_error(self, run_script, tmp_path, sample_index_content):
        """Should return error when no CLAUDE_SESSION_ID is available."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        # Ensure no session ID env vars are set
        env_vars = {
            "CLAUDE_SESSION_ID": "",
            "CLAUDE_CODE_TASK_LIST_ID": "",
        }
        result = run_script(planning_dir, env_vars=env_vars)

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "CLAUDE_SESSION_ID" in output["error"]
        assert output["tasks_written"] == 0
        assert output["task_list_source"] == "none"

    def test_writes_tasks_with_session_id(self, run_script, tmp_path, sample_index_content):
        """Should write batch + section task files when CLAUDE_SESSION_ID is set."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        # Use a test session ID with custom tasks dir
        session_id = "test-session-generate-section-tasks"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        # Clean up any existing tasks
        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["success"] is True
            assert output["state"] == "has_index"
            # With INSERT behavior: 1 batch + 4 sections + 2 (final + output) = 7 tasks
            assert output["tasks_written"] == 7
            assert output["task_list_id"] == session_id
            assert output["task_list_source"] == "session"

            # Verify task files were written
            assert tasks_dir.exists()
            task_files = list(tasks_dir.glob("*.json"))
            assert len(task_files) == 7

            # Position 19 is batch task (INSERT position)
            task_19 = json.loads((tasks_dir / "19.json").read_text())
            assert task_19["subject"] == "Run batch 1 section subagents"

            # Positions 20-23 are section tasks
            for pos in range(20, 24):
                task_file = tasks_dir / f"{pos}.json"
                assert task_file.exists(), f"Task file {pos}.json should exist"
                task_data = json.loads(task_file.read_text())
                assert task_data["id"] == str(pos)
                assert "Write section-" in task_data["subject"]

            # Position 24 is Final Verification, Position 25 is Output Summary
            task_24 = json.loads((tasks_dir / "24.json").read_text())
            assert "Final Verification" in task_24["subject"]

            task_25 = json.loads((tasks_dir / "25.json").read_text())
            assert "Output Summary" in task_25["subject"]

        finally:
            # Cleanup
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_task_file_status_determination(self, run_script, tmp_path, sample_index_content):
        """Batch and all sections in first batch should be in_progress."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        session_id = "test-session-status-determination"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0

            # Batch task (position 19) should be in_progress (ready to work on)
            task_19 = json.loads((tasks_dir / "19.json").read_text())
            assert task_19["status"] == "in_progress"
            assert task_19["subject"] == "Run batch 1 section subagents"

            # All sections in the batch are in_progress (parallel within batch)
            for pos in range(20, 24):
                task_data = json.loads((tasks_dir / f"{pos}.json").read_text())
                assert task_data["status"] == "in_progress"

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_completed_sections_have_completed_status(self, run_script, tmp_path, sample_index_content):
        """Sections with existing files should have completed status, batch still in_progress."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)
        # First two sections are complete
        (sections_dir / "section-01-setup.md").write_text("# Section 1")
        (sections_dir / "section-02-api.md").write_text("# Section 2")

        session_id = "test-session-completed-sections"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["stats"]["completed"] == 2
            assert output["stats"]["missing"] == 2

            # Batch (position 19) is still in_progress (not all sections complete)
            assert json.loads((tasks_dir / "19.json").read_text())["status"] == "in_progress"

            # First two sections (positions 20-21) should be completed
            assert json.loads((tasks_dir / "20.json").read_text())["status"] == "completed"
            assert json.loads((tasks_dir / "21.json").read_text())["status"] == "completed"

            # Remaining sections (positions 22-23) should be in_progress (part of active batch)
            assert json.loads((tasks_dir / "22.json").read_text())["status"] == "in_progress"
            assert json.loads((tasks_dir / "23.json").read_text())["status"] == "in_progress"

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_dependency_chain_in_task_files(self, run_script, tmp_path, sample_index_content):
        """Task files should have correct blockedBy/blocks dependencies."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        session_id = "test-session-dependency-chain"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0

            # Batch task (position 19) should be blocked by create-section-index (position 17)
            # Position mapping: step 18 (create-section-index) -> position 17
            task_19 = json.loads((tasks_dir / "19.json").read_text())
            assert "17" in task_19["blockedBy"]
            # Batch blocks all its sections
            assert "20" in task_19["blocks"]
            assert "21" in task_19["blocks"]
            assert "22" in task_19["blocks"]
            assert "23" in task_19["blocks"]

            # All sections should be blocked by their batch (position 19)
            for pos in range(20, 24):
                task = json.loads((tasks_dir / f"{pos}.json").read_text())
                assert "19" in task["blockedBy"]

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_marks_extra_tasks_obsolete(self, run_script, tmp_path):
        """Extra existing tasks beyond section count should be marked obsolete."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        # Only 2 sections
        index_content = """<!-- SECTION_MANIFEST
section-01-one
section-02-two
END_MANIFEST -->
"""
        (sections_dir / "index.md").write_text(index_content)

        session_id = "test-session-mark-obsolete"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            tasks_dir.mkdir(parents=True)

            # Pre-create extra task files (from a previous larger plan)
            # With INSERT behavior: 1 batch + 2 sections + 2 (final+output) = 5 tasks at positions 19-23
            # So position 25 is the extra task that should be marked obsolete
            (tasks_dir / "25.json").write_text(json.dumps({
                "id": "25",
                "subject": "Write section-03-old.md",
                "status": "pending",
                "blocks": [],
                "blockedBy": [],
            }))

            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0
            output = json.loads(result.stdout)
            # With INSERT: 1 batch + 2 sections + 2 (final+output) = 5 tasks
            assert output["tasks_written"] == 5

            # Position 19 should be batch task
            task_19 = json.loads((tasks_dir / "19.json").read_text())
            assert task_19["subject"] == "Run batch 1 section subagents"

            # Positions 20, 21 should have section tasks
            task_20 = json.loads((tasks_dir / "20.json").read_text())
            assert task_20["subject"] == "Write section-01-one.md"

            task_21 = json.loads((tasks_dir / "21.json").read_text())
            assert task_21["subject"] == "Write section-02-two.md"

            # Positions 22, 23 should have Final Verification and Output Summary
            task_22 = json.loads((tasks_dir / "22.json").read_text())
            assert "Final Verification" in task_22["subject"]

            task_23 = json.loads((tasks_dir / "23.json").read_text())
            assert "Output Summary" in task_23["subject"]

            # Position 25 should be marked obsolete (was pre-created)
            task_25 = json.loads((tasks_dir / "25.json").read_text())
            assert task_25["subject"] == "[obsolete]"
            assert task_25["status"] == "completed"

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_output_includes_task_list_context(self, run_script, tmp_path, sample_index_content):
        """Output should include task_list_id and task_list_source."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        result = run_script(planning_dir)

        # Will fail due to no session ID, but should still have context fields
        output = json.loads(result.stdout)

        assert "task_list_id" in output
        assert "task_list_source" in output
        # Without env vars, should be none
        assert output["task_list_source"] == "none"

    def test_eight_sections_batch_status(self, run_script, tmp_path):
        """Eight sections should have correct batch status determination."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        index_content = """<!-- SECTION_MANIFEST
section-01-one
section-02-two
section-03-three
section-04-four
section-05-five
section-06-six
section-07-seven
section-08-eight
END_MANIFEST -->
"""
        (sections_dir / "index.md").write_text(index_content)

        session_id = "test-session-batch-status"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0
            output = json.loads(result.stdout)
            # With INSERT: 2 batches + 8 sections + 2 (final+output) = 12 tasks
            assert output["tasks_written"] == 12

            # Batch 1 (position 19): in_progress (first incomplete batch)
            task_19 = json.loads((tasks_dir / "19.json").read_text())
            assert task_19["subject"] == "Run batch 1 section subagents"
            assert task_19["status"] == "in_progress"

            # All sections in batch 1 (positions 20-26) are in_progress (parallel within batch)
            for pos in range(20, 27):
                task_data = json.loads((tasks_dir / f"{pos}.json").read_text())
                assert task_data["status"] == "in_progress", f"Position {pos} should be in_progress"

            # Batch 2 (position 27): pending (previous batch not complete)
            task_27 = json.loads((tasks_dir / "27.json").read_text())
            assert task_27["subject"] == "Run batch 2 section subagents"
            assert task_27["status"] == "pending"

            # Section 8 (position 28): pending (batch 2 is pending)
            task_28 = json.loads((tasks_dir / "28.json").read_text())
            assert task_28["subject"] == "Write section-08-eight.md"
            assert task_28["status"] == "pending"

            # Final Verification (position 29) and Output Summary (position 30) exist
            task_29 = json.loads((tasks_dir / "29.json").read_text())
            assert "Final Verification" in task_29["subject"]

            task_30 = json.loads((tasks_dir / "30.json").read_text())
            assert "Output Summary" in task_30["subject"]

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_task_file_format(self, run_script, tmp_path, sample_index_content):
        """Task files should have all required fields in correct format."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        session_id = "test-session-file-format"
        tasks_dir = Path.home() / ".claude" / "tasks" / session_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {"CLAUDE_SESSION_ID": session_id}
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0

            # Check batch task file (position 19) has all required fields
            task_19 = json.loads((tasks_dir / "19.json").read_text())

            assert "id" in task_19
            assert "subject" in task_19
            assert "description" in task_19
            assert "activeForm" in task_19
            assert "status" in task_19
            assert "blocks" in task_19
            assert "blockedBy" in task_19

            # Verify batch task field values
            assert task_19["id"] == "19"
            assert task_19["subject"] == "Run batch 1 section subagents"
            assert "batch 1" in task_19["description"]
            assert task_19["activeForm"] == "Running batch 1 subagents"
            assert task_19["status"] in ("pending", "in_progress", "completed")
            assert isinstance(task_19["blocks"], list)
            assert isinstance(task_19["blockedBy"], list)

            # Check first section task file (position 20) has correct format
            task_20 = json.loads((tasks_dir / "20.json").read_text())

            assert task_20["id"] == "20"
            assert task_20["subject"] == "Write section-01-setup.md"
            assert task_20["description"] == "Write section file: section-01-setup.md"
            assert task_20["activeForm"] == "Writing section-01-setup.md"
            assert task_20["status"] in ("pending", "in_progress", "completed")
            assert isinstance(task_20["blocks"], list)
            assert isinstance(task_20["blockedBy"], list)

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)

    def test_user_specified_task_list_id(self, run_script, tmp_path, sample_index_content):
        """CLAUDE_CODE_TASK_LIST_ID should be preferred over CLAUDE_SESSION_ID."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        (sections_dir / "index.md").write_text(sample_index_content)

        user_task_list_id = "user-specified-task-list"
        session_id = "session-id-should-be-ignored"
        tasks_dir = Path.home() / ".claude" / "tasks" / user_task_list_id

        if tasks_dir.exists():
            import shutil
            shutil.rmtree(tasks_dir)

        try:
            env_vars = {
                "CLAUDE_CODE_TASK_LIST_ID": user_task_list_id,
                "CLAUDE_SESSION_ID": session_id,
            }
            result = run_script(planning_dir, env_vars=env_vars)

            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["task_list_id"] == user_task_list_id
            assert output["task_list_source"] == "user_env"

            # Verify tasks written to user-specified location
            assert tasks_dir.exists()
            assert (tasks_dir / "22.json").exists()

        finally:
            if tasks_dir.exists():
                import shutil
                shutil.rmtree(tasks_dir)
