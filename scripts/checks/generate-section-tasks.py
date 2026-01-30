#!/usr/bin/env python3
"""Generate section-specific tasks for the deep-plan workflow.

This script generates and writes section tasks directly to disk.
Called at step 19 after index.md is created in step 18.

Section tasks INSERT at position 19 (replacing "Write Section Files").
Final Verification and Output Summary shift to positions after all section tasks.

Writes task files to ~/.claude/tasks/<task_list_id>/ starting at position 19.

Usage:
    uv run generate-section-tasks.py --planning-dir "/path/to/planning" --session-id "xxx"

Output:
    JSON with success/failure and tasks_written count.
    Claude should run TaskList to verify the tasks are visible.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.sections import check_section_progress
from lib.task_reconciliation import TaskListContext
from lib.task_storage import (
    SECTION_INSERT_POSITION,
    TaskToWrite,
    build_dependency_graph,
    build_section_dependencies,
    calculate_task_positions,
    generate_section_tasks_to_write,
    write_tasks,
)
from lib.tasks import TaskStatus


def generate_section_tasks(
    planning_dir: Path,
    context_session_id: str | None = None,
) -> dict:
    """Generate and write section tasks directly to disk.

    Args:
        planning_dir: Path to planning directory
        context_session_id: Session ID from --session-id arg (from hook's additionalContext)

    Returns:
        dict with:
        - success: bool
        - error: error message if failed
        - task_list_id: the task list ID used (or null)
        - task_list_source: "context" | "user_env" | "session" | "none"
        - session_id_matched: True/False/None diagnostic
        - tasks_written: number of task files written
        - state: current section state
        - stats: {total, completed, missing}
    """
    context = TaskListContext.from_args_and_env(context_session_id=context_session_id)
    progress = check_section_progress(planning_dir)
    state = progress["state"]

    base_result = {
        "task_list_id": context.task_list_id,
        "task_list_source": str(context.source),
        "session_id_matched": context.session_id_matched,
        "state": state,
    }

    # Handle error states
    if state == "fresh":
        return {
            **base_result,
            "success": False,
            "error": "No sections/index.md found. Create the section index first (step 18).",
            "tasks_written": 0,
            "stats": {"total": 0, "completed": 0, "missing": 0},
        }

    if state == "invalid_index":
        index_format = progress.get("index_format", {})
        error_msg = index_format.get("error", "SECTION_MANIFEST block is invalid")
        return {
            **base_result,
            "success": False,
            "error": f"Invalid index.md: {error_msg}",
            "tasks_written": 0,
            "stats": {"total": 0, "completed": 0, "missing": 0},
        }

    # Handle complete state
    if state == "complete":
        return {
            **base_result,
            "success": True,
            "error": None,
            "tasks_written": 0,
            "stats": {
                "total": len(progress["defined_sections"]),
                "completed": len(progress["completed_sections"]),
                "missing": 0,
            },
            "message": "All sections already complete. No tasks to write.",
        }

    # Check for task list ID
    if not context.task_list_id:
        return {
            **base_result,
            "success": False,
            "error": "No CLAUDE_SESSION_ID available. Session hook may not have run.",
            "tasks_written": 0,
            "stats": {
                "total": len(progress["defined_sections"]),
                "completed": len(progress["completed_sections"]),
                "missing": len(progress["missing_sections"]),
            },
        }

    # Generate section tasks starting at position 19 (INSERT behavior)
    section_tasks, section_deps, section_task_count = generate_section_tasks_to_write(
        planning_dir=planning_dir,
        start_position=SECTION_INSERT_POSITION,
    )

    if not section_tasks:
        return {
            **base_result,
            "success": True,
            "error": None,
            "tasks_written": 0,
            "stats": {
                "total": len(progress["defined_sections"]),
                "completed": len(progress["completed_sections"]),
                "missing": len(progress["missing_sections"]),
            },
            "message": "No section tasks to write.",
        }

    # Calculate shifted positions for Final Verification and Output Summary
    positions = calculate_task_positions(section_task_count)
    final_ver_pos = positions["final-verification"]
    output_summary_pos = positions["output-summary"]

    # Build semantic_id -> position mapping for all tasks
    semantic_to_position: dict[str, int] = {}

    # create-section-index is step 18, position = step - 1 = 17
    # Actually step 18 maps to position 18 (see TASK_IDS: step 18 -> position 17... wait no)
    # Let me check: TASK_IDS has step 18 -> "create-section-index"
    # Position = step - 1 = 17? No wait, the mapping in setup-planning-session is:
    # Context tasks: positions 1-4
    # Workflow tasks: step 6 -> position 5, step 7 -> position 6, ..., step 22 -> position 21
    # So step 18 -> position 17? No wait: step - 1 for steps 6+, but we have 4 context tasks
    # Actually looking at build_semantic_to_position_map(): position = step_num - 1
    # So step 18 -> position 17
    # But generate-section-tasks is step 19 -> position 18
    # And section tasks start at position 19 (SECTION_INSERT_POSITION)
    semantic_to_position["create-section-index"] = 17
    semantic_to_position["generate-section-tasks"] = 18
    semantic_to_position["final-verification"] = final_ver_pos
    semantic_to_position["output-summary"] = output_summary_pos

    # Batch and section tasks map to their positions
    for task in section_tasks:
        if task.subject.startswith("Run batch "):
            # Extract batch number from subject "Run batch N section subagents"
            batch_num = task.subject.split()[2]
            semantic_to_position[f"batch-{batch_num}"] = task.position
        else:
            # Section task
            semantic_to_position[f"section-{task.position}"] = task.position

    # Add Final Verification and Output Summary tasks at shifted positions
    all_tasks = list(section_tasks)  # Copy to avoid mutating original
    all_tasks.append(
        TaskToWrite(
            position=final_ver_pos,
            subject="Final Verification",
            status=TaskStatus.PENDING,
            description="Run check-sections.py to verify all sections complete",
            active_form="Running final verification",
        )
    )
    all_tasks.append(
        TaskToWrite(
            position=output_summary_pos,
            subject="Output Summary",
            status=TaskStatus.PENDING,
            description="Print generated files and next steps",
            active_form="Outputting summary",
        )
    )

    # Build section dependencies for shifted tasks
    shifted_deps = build_section_dependencies(
        section_tasks,
        final_ver_pos,
        output_summary_pos,
    )
    all_deps = {**section_deps, **shifted_deps}

    # Build dependency graph for all tasks
    dependency_graph = build_dependency_graph(
        all_tasks,
        all_deps,
        semantic_to_position,
    )

    # Write all tasks directly to disk
    write_result = write_tasks(
        context.task_list_id,
        all_tasks,
        dependency_graph=dependency_graph,
        mark_extra_obsolete=True,
    )

    if not write_result.success:
        return {
            **base_result,
            "success": False,
            "error": write_result.error,
            "tasks_written": 0,
            "stats": {
                "total": len(progress["defined_sections"]),
                "completed": len(progress["completed_sections"]),
                "missing": len(progress["missing_sections"]),
            },
        }

    return {
        **base_result,
        "success": True,
        "error": None,
        "tasks_written": write_result.tasks_written,
        "stats": {
            "total": len(progress["defined_sections"]),
            "completed": len(progress["completed_sections"]),
            "missing": len(progress["missing_sections"]),
        },
        "message": f"{write_result.tasks_written} section tasks written. Run TaskList to see them.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate section-specific tasks for deep-plan workflow"
    )
    parser.add_argument(
        "--planning-dir",
        required=True,
        type=Path,
        help="Path to planning directory"
    )
    parser.add_argument(
        "--session-id",
        help="Session ID from hook's additionalContext (takes precedence over env vars)"
    )
    args = parser.parse_args()

    result = generate_section_tasks(
        args.planning_dir,
        context_session_id=args.session_id,
    )
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
