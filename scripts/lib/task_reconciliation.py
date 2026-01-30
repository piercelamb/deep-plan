"""Task reconciliation for deep-plan workflow.

This module handles synchronizing the expected task state (based on planning
directory files) with the actual Claude Code task list. It reads task files
from ~/.claude/tasks/<task_list_id>/ and computes exact TaskCreate/TaskUpdate
operations for Claude to execute.

Key concepts:
- CLAUDE_CODE_TASK_LIST_ID: User-specified task list for sharing across sessions
- CLAUDE_SESSION_ID: Auto-captured session ID from SessionStart hook
- Conflict: Only when CLAUDE_CODE_TASK_LIST_ID is set AND has existing tasks
- Position-based matching: Tasks are matched by numeric ID (position), NOT by subject

IMPORTANT: Position-Based Reconciliation
-----------------------------------------
Tasks are matched by POSITION (1, 2, 3...), NOT by subject. This means:
- Position 1 -> 1.json, Position 2 -> 2.json, etc.
- Existing positions (1 to N) are TRANSFORMED via TaskUpdate
- New positions (beyond N) are CREATED via TaskCreate
- TaskUpdate can change subject, description, activeForm, AND status
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self


class TaskListSource(StrEnum):
    """Source of the task list ID."""

    CONTEXT = "context"  # From --session-id arg (hook's additionalContext)
    USER_ENV = "user_env"  # From CLAUDE_CODE_TASK_LIST_ID
    SESSION = "session"  # From CLAUDE_SESSION_ID env var
    NONE = "none"  # No task list ID available


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskListContext:
    """Context about the task list being used."""

    task_list_id: str | None
    source: TaskListSource
    is_user_specified: bool  # True if CLAUDE_CODE_TASK_LIST_ID was set
    # Diagnostic: if both context and env present, did they match?
    session_id_matched: bool | None = None

    @classmethod
    def from_env(cls) -> Self:
        """Get task list context from environment variables only.

        DEPRECATED: Use from_args_and_env() instead for /clear support.

        Priority: CLAUDE_CODE_TASK_LIST_ID > CLAUDE_SESSION_ID

        Returns:
            TaskListContext with task_list_id, source, and is_user_specified
        """
        return cls.from_args_and_env(context_session_id=None)

    @classmethod
    def from_args_and_env(cls, context_session_id: str | None = None) -> Self:
        """Get task list context from CLI args and environment.

        Priority: --session-id (context) > CLAUDE_CODE_TASK_LIST_ID > CLAUDE_SESSION_ID

        The context_session_id comes from the hook's additionalContext output,
        which Claude passes via --session-id argument. This is the most reliable
        source because it works correctly after /clear commands.

        Args:
            context_session_id: Session ID from --session-id arg (passed by Claude
                from hook's additionalContext output)

        Returns:
            TaskListContext with task_list_id, source, is_user_specified, and
            session_id_matched diagnostic field
        """
        env_session_id = os.environ.get("CLAUDE_SESSION_ID")
        user_specified = os.environ.get("CLAUDE_CODE_TASK_LIST_ID")

        # Track if context and env matched (useful for debugging /clear issues)
        session_id_matched = None
        if context_session_id and env_session_id:
            session_id_matched = context_session_id == env_session_id

        # Priority 1: --session-id from hook's additionalContext (most reliable)
        if context_session_id:
            return cls(
                task_list_id=context_session_id,
                source=TaskListSource.CONTEXT,
                is_user_specified=False,
                session_id_matched=session_id_matched,
            )

        # Priority 2: User-specified task list ID
        if user_specified:
            return cls(
                task_list_id=user_specified,
                source=TaskListSource.USER_ENV,
                is_user_specified=True,
            )

        # Priority 3: Session ID from env var (may be stale after /clear)
        if env_session_id:
            return cls(
                task_list_id=env_session_id,
                source=TaskListSource.SESSION,
                is_user_specified=False,
            )

        return cls(
            task_list_id=None,
            source=TaskListSource.NONE,
            is_user_specified=False,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrentTask:
    """A task read from the task list directory."""

    id: str
    subject: str
    status: str
    description: str
    active_form: str


def read_current_tasks(task_list_id: str | None) -> dict[int, CurrentTask]:
    """Read current tasks from ~/.claude/tasks/<task_list_id>/

    IMPORTANT: Tasks are keyed by their numeric ID (position), NOT by subject.
    This enables position-based reconciliation where we transform existing tasks
    by position rather than trying to match by subject.

    Args:
        task_list_id: The task list ID (session ID or user-specified)

    Returns:
        Dict of {id (int): CurrentTask}
    """
    if not task_list_id:
        return {}

    tasks_dir = Path.home() / ".claude" / "tasks" / task_list_id
    if not tasks_dir.exists():
        return {}

    tasks: dict[int, CurrentTask] = {}
    for task_file in sorted(tasks_dir.glob("*.json")):
        try:
            with open(task_file) as f:
                task_data = json.load(f)
                task_id = int(task_data["id"])  # Numeric ID for position-based matching
                task = CurrentTask(
                    id=task_data["id"],  # Keep string version for TaskUpdate
                    subject=task_data["subject"],
                    status=task_data["status"],
                    description=task_data.get("description", ""),
                    active_form=task_data.get("activeForm", ""),
                )
                tasks[task_id] = task
        except (json.JSONDecodeError, KeyError, ValueError):
            # Skip invalid task files (ValueError for non-numeric IDs)
            continue

    return tasks


@dataclass(frozen=True, slots=True, kw_only=True)
class ConflictInfo:
    """Information about a task list conflict."""

    task_list_id: str
    existing_task_count: int
    sample_subjects: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        return {
            "task_list_id": self.task_list_id,
            "existing_task_count": self.existing_task_count,
            "sample_subjects": self.sample_subjects,
        }


def check_for_conflict(
    context: TaskListContext,
    current_tasks: dict[int, CurrentTask],
) -> ConflictInfo | None:
    """Check if user-specified task list has existing tasks.

    IMPORTANT: Conflict detection ONLY applies when CLAUDE_CODE_TASK_LIST_ID
    is set by the user. If we're using CLAUDE_SESSION_ID and find existing
    tasks, that's just a normal resume scenario, not a conflict.

    Args:
        context: The task list context
        current_tasks: Dict of current tasks by numeric ID (position)

    Returns:
        ConflictInfo if user should be prompted, None otherwise
    """
    # Only check for conflicts when user explicitly set CLAUDE_CODE_TASK_LIST_ID
    if not context.is_user_specified:
        return None

    if not current_tasks:
        return None

    # User set CLAUDE_CODE_TASK_LIST_ID and there are existing tasks
    # This is a potential conflict - user may not want to overwrite
    # Get sample subjects from the tasks (sorted by position)
    sample_subjects = [
        current_tasks[pos].subject
        for pos in sorted(current_tasks.keys())[:3]
    ]
    return ConflictInfo(
        task_list_id=context.task_list_id or "",
        existing_task_count=len(current_tasks),
        sample_subjects=sample_subjects,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskOperation:
    """A task operation for Claude to execute."""

    tool: str  # "TaskCreate" or "TaskUpdate"
    params: dict
    reason: str
    then: dict | None = None  # Follow-up operation (for non-pending creates)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        result = {
            "tool": self.tool,
            "params": self.params,
            "reason": self.reason,
        }
        if self.then is not None:
            result["then"] = self.then
        return result


def compute_operations(
    expected_tasks: list[dict],
    current_tasks: dict[int, CurrentTask],
) -> list[TaskOperation]:
    """Compute exact TaskCreate/TaskUpdate operations using POSITION-BASED matching.

    CRITICAL: Tasks are matched by POSITION (1, 2, 3...), NOT by subject.
    - Positions with existing tasks: Compare fields, TaskUpdate only if different
    - Positions with matching tasks: NO operation (already correct)
    - Positions beyond existing: TaskCreate for new tasks
    - Extra existing positions: Mark as [obsolete] + completed

    Args:
        expected_tasks: List of {subject, status, description, activeForm} in order
        current_tasks: Dict of {id (int): CurrentTask} keyed by numeric ID

    Returns:
        List of TaskOperation ready for Claude to execute (empty if all match)
    """
    operations: list[TaskOperation] = []
    max_existing_id = max(current_tasks.keys()) if current_tasks else 0

    for position, expected in enumerate(expected_tasks, start=1):
        expected_subject = expected["subject"]
        expected_status = expected["status"]
        # Only default to subject if description is truly missing (None), not empty string
        expected_description = expected.get("description")
        if expected_description is None:
            expected_description = expected_subject
        expected_active_form = expected.get("activeForm", "")

        if position <= max_existing_id and position in current_tasks:
            # Position exists - TRANSFORM via TaskUpdate
            current = current_tasks[position]

            # Check what fields need updating
            needs_subject_update = current.subject != expected_subject
            needs_status_update = current.status != expected_status
            needs_description_update = current.description != expected_description
            needs_active_form_update = current.active_form != expected_active_form

            needs_update = (
                needs_subject_update
                or needs_status_update
                or needs_description_update
                or needs_active_form_update
            )

            if needs_update:
                update_params: dict = {"taskId": current.id}

                # Only include fields that differ
                if needs_subject_update:
                    update_params["subject"] = expected_subject
                if needs_status_update:
                    update_params["status"] = expected_status
                if needs_description_update:
                    update_params["description"] = expected_description
                if needs_active_form_update:
                    update_params["activeForm"] = expected_active_form

                # Truncate subjects for reason string
                current_truncated = current.subject[:30] + "..." if len(current.subject) > 30 else current.subject
                expected_truncated = expected_subject[:30] + "..." if len(expected_subject) > 30 else expected_subject

                operations.append(
                    TaskOperation(
                        tool="TaskUpdate",
                        params=update_params,
                        reason=f"Transform position {position}: '{current_truncated}' -> '{expected_truncated}'",
                    )
                )
        else:
            # Position doesn't exist - CREATE new task
            then_op = None
            # If status should be non-pending, add follow-up update
            if expected_status != "pending":
                then_op = {
                    "tool": "TaskUpdate",
                    "params": {
                        "status": expected_status,
                    },
                    "note": "TaskCreate returns the new taskId - use it here",
                }

            operations.append(
                TaskOperation(
                    tool="TaskCreate",
                    params={
                        "subject": expected_subject,
                        "description": expected_description,
                        "activeForm": expected_active_form,
                    },
                    reason=f"New task at position {position}",
                    then=then_op,
                )
            )

    # Handle extra existing positions (more existing than expected)
    # Mark them as obsolete so they don't clutter the task list
    expected_count = len(expected_tasks)
    for extra_position in sorted(current_tasks.keys()):
        if extra_position > expected_count:
            current = current_tasks[extra_position]
            # Skip if already marked obsolete
            if current.subject == "[obsolete]" and current.status == "completed":
                continue
            operations.append(
                TaskOperation(
                    tool="TaskUpdate",
                    params={
                        "taskId": current.id,
                        "subject": "[obsolete]",
                        "status": "completed",
                    },
                    reason=f"Mark position {extra_position} obsolete (beyond expected {expected_count} tasks)",
                )
            )

    return operations


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationResult:
    """Result of task reconciliation."""

    success: bool
    task_list_id: str | None
    task_list_source: TaskListSource
    planning_dir: str
    operations: list[TaskOperation]
    conflict: ConflictInfo | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        result: dict = {
            "success": self.success,
            "task_list_id": self.task_list_id,
            "task_list_source": str(self.task_list_source),
            "planning_dir": self.planning_dir,
            "operations": [op.to_dict() for op in self.operations],
        }

        if self.conflict is not None:
            result["conflict"] = self.conflict.to_dict()

        if self.message is not None:
            result["message"] = self.message

        return result


def reconcile_tasks(
    planning_dir: Path,
    expected_tasks: list[dict],
) -> ReconciliationResult:
    """Main entry point for task reconciliation.

    Args:
        planning_dir: Path to the planning directory
        expected_tasks: List of expected task dicts with subject, status, etc.

    Returns:
        ReconciliationResult with operations for Claude to execute
    """
    # 1. Get task list context from environment
    context = TaskListContext.from_env()

    # 2. Read current tasks from disk (empty if no task_list_id)
    current_tasks = read_current_tasks(context.task_list_id)

    # 3. Check for conflict (only if CLAUDE_CODE_TASK_LIST_ID was set)
    conflict = check_for_conflict(context, current_tasks)

    # 4. Compute operations
    operations = compute_operations(expected_tasks, current_tasks)

    # 5. Build result
    return ReconciliationResult(
        success=True,
        task_list_id=context.task_list_id,
        task_list_source=context.source,
        planning_dir=str(planning_dir),
        operations=operations,
        conflict=conflict,
    )
