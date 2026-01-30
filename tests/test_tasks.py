"""Tests for tasks.py - task definitions and generation."""

import pytest

from scripts.lib.tasks import (
    BATCH_SIZE,
    TASK_DEFINITIONS,
    TASK_DEPENDENCIES,
    TASK_IDS,
    TASK_ID_TO_STEP,
    STEP_NAMES,
    TaskStatus,
    TaskDefinition,
    create_context_tasks,
    generate_expected_tasks,
)


class TestTaskIdMapping:
    """Tests for TASK_IDS and TASK_ID_TO_STEP mappings."""

    def test_task_ids_has_all_workflow_steps(self):
        """Verify all workflow steps (6-22) have task IDs."""
        expected_steps = {6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}
        actual_steps = set(TASK_IDS.keys())
        assert actual_steps == expected_steps

    def test_task_id_to_step_is_inverse(self):
        """Verify TASK_ID_TO_STEP is exact inverse of TASK_IDS."""
        for step, task_id in TASK_IDS.items():
            assert TASK_ID_TO_STEP[task_id] == step

    def test_all_task_ids_unique(self):
        """Verify all task IDs are unique."""
        task_ids = list(TASK_IDS.values())
        assert len(task_ids) == len(set(task_ids))


class TestDependencyGraph:
    """Tests for TASK_DEPENDENCIES validity."""

    def test_all_dependencies_exist(self):
        """Verify all blockedBy references point to existing tasks."""
        # All valid task IDs (workflow tasks + context task IDs)
        all_task_ids = set(TASK_DEFINITIONS.keys()) | set(TASK_DEPENDENCIES.keys())
        for task_id, deps in TASK_DEPENDENCIES.items():
            for dep in deps:
                assert dep in all_task_ids, f"Task {task_id} depends on non-existent task {dep}"

    def test_no_self_dependencies(self):
        """Verify no task depends on itself."""
        for task_id, deps in TASK_DEPENDENCIES.items():
            assert task_id not in deps, f"Task {task_id} depends on itself"

    def test_no_circular_dependencies(self):
        """Verify there are no circular dependencies."""
        def has_cycle(task_id: str, visited: set, path: set) -> bool:
            if task_id in path:
                return True
            if task_id in visited:
                return False
            visited.add(task_id)
            path.add(task_id)
            for dep in TASK_DEPENDENCIES.get(task_id, []):
                if has_cycle(dep, visited, path):
                    return True
            path.remove(task_id)
            return False

        visited: set[str] = set()
        for task_id in TASK_DEPENDENCIES:
            assert not has_cycle(task_id, visited, set()), f"Circular dependency detected involving {task_id}"

    def test_context_tasks_blocked_by_output_summary(self):
        """Verify all context tasks are blocked by output-summary."""
        context_task_ids = [
            "context-plugin-root",
            "context-planning-dir",
            "context-initial-file",
            "context-review-mode",
        ]
        for task_id in context_task_ids:
            assert task_id in TASK_DEPENDENCIES, f"Context task {task_id} missing from dependencies"
            assert "output-summary" in TASK_DEPENDENCIES[task_id], f"Context task {task_id} not blocked by output-summary"

    def test_workflow_chain_integrity(self):
        """Verify main workflow forms a complete chain."""
        # research-decision should have no dependencies
        assert TASK_DEPENDENCIES["research-decision"] == []
        # output-summary should be at the end
        assert TASK_DEPENDENCIES["output-summary"] == ["final-verification"]


class TestTaskDefinitions:
    """Tests for TASK_DEFINITIONS completeness."""

    def test_all_workflow_task_ids_have_definitions(self):
        """Verify every workflow task ID has a definition."""
        # Note: Context tasks are generated dynamically, not in TASK_DEFINITIONS
        workflow_task_ids = set(TASK_IDS.values())
        defined_tasks = set(TASK_DEFINITIONS.keys())
        assert workflow_task_ids == defined_tasks

    def test_all_definitions_have_required_fields(self):
        """Verify all definitions have subject, description, active_form."""
        for task_id, defn in TASK_DEFINITIONS.items():
            assert isinstance(defn, TaskDefinition)
            assert defn.subject, f"Task {task_id} missing subject"
            assert defn.description, f"Task {task_id} missing description"
            assert defn.active_form, f"Task {task_id} missing active_form"

    def test_task_definition_to_dict(self):
        """Verify TaskDefinition.to_dict() returns correct structure."""
        defn = TaskDefinition(
            subject="Test",
            description="Test description",
            active_form="Testing",
        )
        result = defn.to_dict()
        assert result == {
            "subject": "Test",
            "description": "Test description",
            "activeForm": "Testing",
        }


class TestContextTasks:
    """Tests for create_context_tasks()."""

    def test_creates_four_tasks(self):
        """Verify 4 individual context tasks are created."""
        tasks = create_context_tasks(
            plugin_root="/path/to/plugin",
            planning_dir="/path/to/planning",
            initial_file="/path/to/spec.md",
            review_mode="external_llm",
        )
        assert len(tasks) == 4

    def test_task_ids_are_correct(self):
        """Verify context tasks have correct IDs."""
        tasks = create_context_tasks(
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="skip",
        )
        ids = [t["id"] for t in tasks]
        assert "context-plugin-root" in ids
        assert "context-planning-dir" in ids
        assert "context-initial-file" in ids
        assert "context-review-mode" in ids

    def test_values_in_subject_field(self):
        """Verify values are stored in subject field (visible after compaction)."""
        tasks = create_context_tasks(
            plugin_root="/plugin",
            planning_dir="/planning",
            initial_file="/spec.md",
            review_mode="opus_subagent",
        )
        task_by_id = {t["id"]: t for t in tasks}

        assert task_by_id["context-plugin-root"]["subject"] == "plugin_root=/plugin"
        assert task_by_id["context-planning-dir"]["subject"] == "planning_dir=/planning"
        assert task_by_id["context-initial-file"]["subject"] == "initial_file=/spec.md"
        assert task_by_id["context-review-mode"]["subject"] == "review_mode=opus_subagent"

    def test_all_blocked_by_output_summary(self):
        """Verify all context tasks are blocked by output-summary."""
        tasks = create_context_tasks(
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="skip",
        )
        for task in tasks:
            assert task["blockedBy"] == ["output-summary"], f"Task {task['id']} not blocked by output-summary"

    def test_all_status_pending(self):
        """Verify all context tasks start as pending."""
        tasks = create_context_tasks(
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="skip",
        )
        for task in tasks:
            assert task["status"] == TaskStatus.PENDING, f"Task {task['id']} not pending"

    def test_all_have_description_and_activeform(self):
        """Verify all context tasks have description and activeForm."""
        tasks = create_context_tasks(
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="skip",
        )
        for task in tasks:
            assert "description" in task
            assert "activeForm" in task
            assert task["description"] == "Session context item"
            assert task["activeForm"] == "Context"


class TestGenerateExpectedTasks:
    """Tests for generate_expected_tasks()."""

    def test_fresh_start_all_pending_except_first(self):
        """Verify fresh start (step 6) has first task in_progress, rest pending."""
        tasks = generate_expected_tasks(
            resume_step=6,
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="external_llm",
        )
        # Find research-decision task
        research = next(t for t in tasks if t["id"] == "research-decision")
        assert research["status"] == TaskStatus.IN_PROGRESS

        # Context tasks should always be pending
        context_ids = {"context-plugin-root", "context-planning-dir", "context-initial-file", "context-review-mode"}
        for task in tasks:
            if task["id"] in context_ids:
                assert task["status"] == TaskStatus.PENDING  # Always pending
            elif task["id"] == "research-decision":
                continue  # Already checked
            else:
                step = TASK_ID_TO_STEP.get(task["id"])
                if step and step > 6:
                    assert task["status"] == TaskStatus.PENDING, f"Task {task['id']} should be pending"

    def test_resume_mid_workflow(self):
        """Verify resuming at step 11 has correct statuses."""
        tasks = generate_expected_tasks(
            resume_step=11,
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="external_llm",
        )
        task_by_id = {t["id"]: t for t in tasks}

        # Steps < 11 should be completed
        assert task_by_id["research-decision"]["status"] == TaskStatus.COMPLETED
        assert task_by_id["execute-research"]["status"] == TaskStatus.COMPLETED
        assert task_by_id["write-spec"]["status"] == TaskStatus.COMPLETED

        # Step 11 should be in_progress
        assert task_by_id["generate-plan"]["status"] == TaskStatus.IN_PROGRESS

        # Steps > 11 should be pending
        assert task_by_id["external-review"]["status"] == TaskStatus.PENDING
        assert task_by_id["output-summary"]["status"] == TaskStatus.PENDING

    def test_includes_context_tasks(self):
        """Verify all 4 context tasks are included."""
        tasks = generate_expected_tasks(
            resume_step=6,
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="external_llm",
        )
        ids = [t["id"] for t in tasks]
        assert "context-plugin-root" in ids
        assert "context-planning-dir" in ids
        assert "context-initial-file" in ids
        assert "context-review-mode" in ids

    def test_context_tasks_have_values_in_subject(self):
        """Verify context tasks have their values in subject field."""
        tasks = generate_expected_tasks(
            resume_step=6,
            plugin_root="/my/plugin",
            planning_dir="/my/planning",
            initial_file="/my/spec.md",
            review_mode="opus_subagent",
        )
        task_by_id = {t["id"]: t for t in tasks}

        assert task_by_id["context-plugin-root"]["subject"] == "plugin_root=/my/plugin"
        assert task_by_id["context-planning-dir"]["subject"] == "planning_dir=/my/planning"
        assert task_by_id["context-initial-file"]["subject"] == "initial_file=/my/spec.md"
        assert task_by_id["context-review-mode"]["subject"] == "review_mode=opus_subagent"

    def test_all_tasks_have_required_fields(self):
        """Verify all tasks have required fields."""
        tasks = generate_expected_tasks(
            resume_step=6,
            plugin_root="/p",
            planning_dir="/d",
            initial_file="/f",
            review_mode="external_llm",
        )
        for task in tasks:
            assert "id" in task
            assert "subject" in task
            assert "description" in task
            assert "activeForm" in task
            assert "status" in task
            assert "blockedBy" in task


class TestConstants:
    """Tests for module constants."""

    def test_batch_size_is_seven(self):
        """Verify BATCH_SIZE is 7 (max concurrent subagents)."""
        assert BATCH_SIZE == 7

    def test_step_names_covers_all_steps(self):
        """Verify STEP_NAMES covers setup and workflow steps."""
        # Setup steps
        assert 0 in STEP_NAMES
        assert 1 in STEP_NAMES
        assert 4 in STEP_NAMES
        # Workflow steps
        for step in TASK_IDS:
            assert step in STEP_NAMES, f"Step {step} missing from STEP_NAMES"
