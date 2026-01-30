"""Direct task file storage for Claude Code Tasks.

Writes task files directly to ~/.claude/tasks/<task_list_id>/
instead of returning operations for Claude to execute.

COUPLING WARNING: This module depends on Claude Code's internal
task storage format. If Anthropic changes the format, this code
will need to be updated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from lib.tasks import TASK_IDS, TaskStatus

# Position constants
CONTEXT_TASK_COUNT = 4  # Positions 1-4
SECTION_INSERT_POSITION = 19  # Where section tasks INSERT (replaces "Write Section Files")


class TaskWriteError(Exception):
    """Raised when task files cannot be written."""

    pass


def get_tasks_dir(task_list_id: str) -> Path:
    """Get the tasks directory for a task list ID."""
    return Path.home() / ".claude" / "tasks" / task_list_id


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrentTask:
    """A task read from disk."""

    position: int
    subject: str
    status: str
    description: str = ""
    blocks: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()


def read_current_tasks(task_list_id: str) -> dict[int, CurrentTask]:
    """Read current tasks from disk.

    Args:
        task_list_id: The task list ID

    Returns:
        Dict mapping position -> CurrentTask
    """
    tasks_dir = get_tasks_dir(task_list_id)
    if not tasks_dir.exists():
        return {}

    result: dict[int, CurrentTask] = {}
    for task_file in tasks_dir.glob("*.json"):
        try:
            position = int(task_file.stem)
            data = json.loads(task_file.read_text())

            # Skip obsolete tasks
            if data.get("subject") == "[obsolete]":
                continue

            result[position] = CurrentTask(
                position=position,
                subject=data.get("subject", ""),
                status=data.get("status", "pending"),
                description=data.get("description", ""),
                blocks=tuple(data.get("blocks", [])),
                blocked_by=tuple(data.get("blockedBy", [])),
            )
        except (ValueError, json.JSONDecodeError):
            continue

    return result


def needs_migration(current_tasks: dict[int, CurrentTask]) -> bool:
    """Check if tasks have old structure that needs migration.

    Old structure (broken):
    - Position 19: "Write Section Files"
    - Position 20: "Final Verification"
    - Position 21: "Output Summary"
    - Positions 22+: Section tasks (batch and section tasks)
    - Final Verification blockedBy 19 (write-sections), NOT the last batch

    New structure (correct):
    - Positions 19+: Section tasks (batch and section tasks)
    - Final Verification at position 19 + section_count
    - Output Summary at position 19 + section_count + 1
    - Final Verification blockedBy last batch

    Returns:
        True if old structure detected (has section at 22+ AND Final Verification at 20)
    """
    # Check for section task at position 22
    has_section_at_22 = False
    if 22 in current_tasks:
        subject_lower = current_tasks[22].subject.lower()
        has_section_at_22 = "batch" in subject_lower or "section" in subject_lower

    # Check for Final Verification at position 20
    has_final_at_20 = False
    if 20 in current_tasks:
        has_final_at_20 = "Final Verification" in current_tasks[20].subject

    return has_section_at_22 and has_final_at_20


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskToWrite:
    """A task to write to disk."""

    position: int
    subject: str
    status: TaskStatus
    description: str = ""
    active_form: str = ""
    blocks: tuple[str, ...] = ()  # Task IDs this task blocks
    blocked_by: tuple[str, ...] = ()  # Task IDs blocking this task

    def to_file_dict(self) -> dict:
        """Convert to dict matching Claude Code task file format."""
        return {
            "id": str(self.position),
            "subject": self.subject,
            "description": self.description,
            "activeForm": self.active_form,
            "status": str(self.status),
            "blocks": list(self.blocks),
            "blockedBy": list(self.blocked_by),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskWriteResult:
    """Result of writing tasks to disk."""

    success: bool
    task_list_id: str
    tasks_written: int
    tasks_dir: Path
    error: str | None = None

    @classmethod
    def ok(cls, task_list_id: str, tasks_written: int, tasks_dir: Path) -> Self:
        return cls(
            success=True,
            task_list_id=task_list_id,
            tasks_written=tasks_written,
            tasks_dir=tasks_dir,
        )

    @classmethod
    def err(cls, task_list_id: str, error: str) -> Self:
        return cls(
            success=False,
            task_list_id=task_list_id,
            tasks_written=0,
            tasks_dir=Path(),
            error=error,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ConflictInfo:
    """Information about existing tasks in a user-specified task list."""

    task_list_id: str
    existing_task_count: int
    sample_subjects: list[str]

    def to_dict(self) -> dict:
        return {
            "task_list_id": self.task_list_id,
            "existing_task_count": self.existing_task_count,
            "sample_subjects": self.sample_subjects,
        }


def check_for_conflict(
    task_list_id: str,
    is_user_specified: bool,
) -> ConflictInfo | None:
    """Check if user-specified task list has existing tasks.

    Only checks when CLAUDE_CODE_TASK_LIST_ID is explicitly set by user.
    Session-based task lists (from CLAUDE_SESSION_ID) never conflict -
    existing tasks there are just a resume scenario.

    Args:
        task_list_id: The task list ID to check
        is_user_specified: True if CLAUDE_CODE_TASK_LIST_ID was set

    Returns:
        ConflictInfo if user should be prompted, None otherwise
    """
    if not is_user_specified:
        return None  # Session-based = no conflict

    tasks_dir = get_tasks_dir(task_list_id)
    if not tasks_dir.exists():
        return None  # No existing tasks

    # Count existing task files
    task_files = list(tasks_dir.glob("*.json"))
    if not task_files:
        return None  # Empty directory

    # Read sample subjects for display
    sample_subjects: list[str] = []
    for task_file in sorted(task_files)[:3]:
        try:
            data = json.loads(task_file.read_text())
            subject = data.get("subject", "")
            if subject and subject != "[obsolete]":
                sample_subjects.append(subject)
        except json.JSONDecodeError:
            continue

    return ConflictInfo(
        task_list_id=task_list_id,
        existing_task_count=len(task_files),
        sample_subjects=sample_subjects,
    )


def calculate_task_positions(
    section_task_count: int = 0,
) -> dict[str, int]:
    """Calculate positions for all tasks including shifts for section insertion.

    Section tasks INSERT at position 19, replacing the "Write Section Files" task.
    Final Verification and Output Summary shift to positions after all section tasks.

    Args:
        section_task_count: Number of section tasks (batches + sections).
            0 means no index.md exists yet - original positions used.

    Returns:
        Dict mapping semantic task IDs to positions.

    Position Layout:
        - Positions 1-4: Context tasks (fixed)
        - Positions 5-18: Workflow tasks up to create-section-index (fixed)
        - Position 19+: Section tasks (batches + sections) OR write-sections
        - Final Verification: 19 + section_task_count (or 20 if no sections)
        - Output Summary: 19 + section_task_count + 1 (or 21 if no sections)
    """
    positions: dict[str, int] = {}

    # Context tasks (positions 1-4) - fixed
    context_ids = [
        "context-plugin-root",
        "context-planning-dir",
        "context-initial-file",
        "context-review-mode",
    ]
    for i, ctx_id in enumerate(context_ids, start=1):
        positions[ctx_id] = i

    # Workflow tasks (positions 5-18)
    # Step 6 -> position 5, step 7 -> position 6, ..., step 19 -> position 18
    # BUT we stop at step 19 (create-section-index) which maps to position 18
    for step_num, task_id in sorted(TASK_IDS.items()):
        position = step_num - 1  # step 6 -> 5, step 19 -> 18
        # Only include tasks up to generate-section-tasks (step 19, position 18)
        # write-sections (step 20) and later get special handling
        if step_num <= 19:
            positions[task_id] = position

    if section_task_count == 0:
        # No sections yet - use original positions
        positions["write-sections"] = 19
        positions["final-verification"] = 20
        positions["output-summary"] = 21
    else:
        # Sections INSERT at 19, shift later tasks
        # Note: "write-sections" task is REPLACED by section tasks, so no entry
        positions["final-verification"] = SECTION_INSERT_POSITION + section_task_count
        positions["output-summary"] = SECTION_INSERT_POSITION + section_task_count + 1

    return positions


def build_section_dependencies(
    section_tasks: list[TaskToWrite],
    final_verification_pos: int,
    output_summary_pos: int,
) -> dict[str, list[str]]:
    """Build dependency map for shifted tasks when sections are inserted.

    When section tasks INSERT at position 19:
    - Final verification is blockedBy the last batch task
    - Output summary is blockedBy final verification
    - Context tasks (1-4) are blockedBy output summary

    Args:
        section_tasks: List of section/batch tasks (from generate_section_tasks_to_write)
        final_verification_pos: Position of final verification (shifted)
        output_summary_pos: Position of output summary (shifted)

    Returns:
        Dict of semantic_id -> list of blockedBy semantic_ids.
        Merge with existing TASK_DEPENDENCIES to get complete graph.
    """
    deps: dict[str, list[str]] = {}

    if not section_tasks:
        return deps

    # Find batch positions
    batch_positions = [t.position for t in section_tasks if "batch" in t.subject.lower()]
    if not batch_positions:
        return deps

    last_batch_pos = max(batch_positions)

    # Final verification is blocked by last batch
    deps["final-verification"] = [f"batch-{_batch_num_for_position(section_tasks, last_batch_pos)}"]

    # Output summary is blocked by final verification
    deps["output-summary"] = ["final-verification"]

    # Context tasks are blocked by output summary
    for ctx_id in ["context-plugin-root", "context-planning-dir", "context-initial-file", "context-review-mode"]:
        deps[ctx_id] = ["output-summary"]

    return deps


def _batch_num_for_position(section_tasks: list[TaskToWrite], position: int) -> int:
    """Get batch number for a given position."""
    for task in section_tasks:
        if task.position == position and "batch" in task.subject.lower():
            # Extract batch number from "Run batch N section subagents"
            parts = task.subject.split()
            for i, part in enumerate(parts):
                if part == "batch" and i + 1 < len(parts):
                    try:
                        return int(parts[i + 1])
                    except ValueError:
                        pass
    return 1  # Default to batch 1


def build_dependency_graph(
    tasks: list[TaskToWrite],
    semantic_dependencies: dict[str, list[str]],
    semantic_to_position: dict[str, int],
) -> dict[int, tuple[list[str], list[str]]]:
    """Build blocks and blockedBy arrays for each task position.

    Args:
        tasks: List of tasks with positions
        semantic_dependencies: Dict of semantic_id -> list of semantic_ids it's blocked by
        semantic_to_position: Dict of semantic_id -> position number

    Returns:
        Dict of position -> (blocks, blockedBy) where each is a list of position strings
    """
    # Initialize empty lists for each position
    blocks: dict[int, list[str]] = {t.position: [] for t in tasks}
    blocked_by: dict[int, list[str]] = {t.position: [] for t in tasks}

    # Build blockedBy from semantic dependencies
    for semantic_id, deps in semantic_dependencies.items():
        if semantic_id not in semantic_to_position:
            continue
        position = semantic_to_position[semantic_id]
        if position not in blocked_by:
            continue
        for dep_id in deps:
            if dep_id in semantic_to_position:
                dep_position = semantic_to_position[dep_id]
                blocked_by[position].append(str(dep_position))

    # Build blocks (inverse of blockedBy)
    for position, deps in blocked_by.items():
        for dep_pos_str in deps:
            dep_pos = int(dep_pos_str)
            if dep_pos in blocks:
                blocks[dep_pos].append(str(position))

    return {pos: (blocks[pos], blocked_by[pos]) for pos in blocks}


def write_tasks(
    task_list_id: str,
    tasks: list[TaskToWrite],
    dependency_graph: dict[int, tuple[list[str], list[str]]] | None = None,
    *,
    mark_extra_obsolete: bool = True,
) -> TaskWriteResult:
    """Write tasks directly to Claude Code task storage.

    Args:
        task_list_id: Session ID or user-specified task list ID
        tasks: List of tasks to write (in position order)
        dependency_graph: Optional dict of position -> (blocks, blockedBy).
            If provided, overrides blocks/blocked_by on TaskToWrite.
        mark_extra_obsolete: If True, marks existing tasks beyond
            the last written position as [obsolete] + completed

    Returns:
        TaskWriteResult with success status and details

    Note: This overwrites existing task files at the same positions.
    """
    if not task_list_id:
        return TaskWriteResult.err("", "No task_list_id provided")

    tasks_dir = get_tasks_dir(task_list_id)

    try:
        # Create directory if needed
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # Track highest position we write to
        max_written_position = 0

        # Write each task
        for task in tasks:
            task_data = task.to_file_dict()

            # Apply dependency graph if provided
            if dependency_graph and task.position in dependency_graph:
                blocks, blocked_by = dependency_graph[task.position]
                task_data["blocks"] = blocks
                task_data["blockedBy"] = blocked_by

            task_file = tasks_dir / f"{task.position}.json"
            task_file.write_text(json.dumps(task_data, indent=2))
            max_written_position = max(max_written_position, task.position)

        # Mark extra existing tasks as obsolete
        if mark_extra_obsolete:
            _mark_extra_obsolete(tasks_dir, max_written_position)

        return TaskWriteResult.ok(
            task_list_id=task_list_id,
            tasks_written=len(tasks),
            tasks_dir=tasks_dir,
        )

    except PermissionError as e:
        return TaskWriteResult.err(task_list_id, f"Permission denied: {e}")
    except OSError as e:
        return TaskWriteResult.err(task_list_id, f"File system error: {e}")


def _mark_extra_obsolete(tasks_dir: Path, max_written_position: int) -> None:
    """Mark existing task files beyond max_written_position as obsolete.

    Preserves existing blocks/blockedBy fields when marking obsolete.
    """
    for task_file in tasks_dir.glob("*.json"):
        try:
            position = int(task_file.stem)
            if position > max_written_position:
                # Read existing, check if already obsolete
                data = json.loads(task_file.read_text())
                if (
                    data.get("subject") == "[obsolete]"
                    and data.get("status") == "completed"
                ):
                    continue  # Already obsolete
                # Mark as obsolete (preserve other fields like blocks/blockedBy)
                data["subject"] = "[obsolete]"
                data["status"] = "completed"
                # Ensure required fields exist
                data.setdefault("blocks", [])
                data.setdefault("blockedBy", [])
                task_file.write_text(json.dumps(data, indent=2))
        except (ValueError, json.JSONDecodeError):
            continue  # Skip non-numeric or invalid files


def generate_section_tasks_to_write(
    planning_dir: Path,
    start_position: int = 19,
) -> tuple[list[TaskToWrite], dict[str, list[str]], int]:
    """Generate batch and section tasks to write based on sections/index.md.

    Section tasks INSERT at position 19 (replacing "Write Section Files").
    This means Final Verification and Output Summary shift to later positions.

    Args:
        planning_dir: Path to planning directory
        start_position: First position for batch/section tasks (default: 19 = INSERT)

    Returns:
        Tuple of:
        - List of TaskToWrite for batches and sections (empty if no valid index)
        - Dict of dependencies (semantic_id -> list of blockedBy semantic_ids)
        - Total count of section tasks generated

    Task structure with batch coordination:
    - batch-1 at position 19, blocked by create-section-index (position 18)
    - sections 1-7 at positions 20-26, all blocked by batch-1
    - batch-2 at position 27 (if needed), blocked by batch-1
    - sections 8-14 at positions 28-34, all blocked by batch-2
    - etc.

    Position formula:
    - batch-N position = start_position + (N-1) * (BATCH_SIZE + 1)
    - section positions in batch N = batch_position + 1 through batch_position + num_sections

    This creates parallel execution within batches:
    batch-1 -> [section-20, section-21, ...] (all parallel, all blocked by batch-1)
    batch-1 -> batch-2 -> [section-28, section-29, ...] (all parallel)
    """
    from lib.sections import check_section_progress
    from lib.tasks import BATCH_SIZE

    progress = check_section_progress(planning_dir)

    # Return empty if no valid index or workflow complete
    if progress["state"] in ("fresh", "invalid_index", "complete"):
        return [], {}, 0

    defined_sections = progress["defined_sections"]
    completed_sections = set(progress["completed_sections"])
    tasks: list[TaskToWrite] = []
    dependencies: dict[str, list[str]] = {}

    num_batches = (len(defined_sections) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(1, num_batches + 1):
        # Calculate positions for this batch
        # batch-N position = start_position + (N-1) * (BATCH_SIZE + 1)
        batch_position = start_position + (batch_num - 1) * (BATCH_SIZE + 1)

        # Get sections for this batch
        start_idx = (batch_num - 1) * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(defined_sections))
        batch_sections = defined_sections[start_idx:end_idx]

        # Determine if this batch is complete (all sections written)
        batch_complete = all(s in completed_sections for s in batch_sections)

        # Determine if this batch should be in_progress
        # A batch is in_progress if it's the first incomplete batch
        prev_batches_complete = True
        for prev_batch in range(1, batch_num):
            prev_start = (prev_batch - 1) * BATCH_SIZE
            prev_end = min(prev_start + BATCH_SIZE, len(defined_sections))
            prev_sections = defined_sections[prev_start:prev_end]
            if not all(s in completed_sections for s in prev_sections):
                prev_batches_complete = False
                break

        if batch_complete:
            batch_status = TaskStatus.COMPLETED
        elif prev_batches_complete:
            batch_status = TaskStatus.IN_PROGRESS
        else:
            batch_status = TaskStatus.PENDING

        # Create batch coordination task
        batch_semantic_id = f"batch-{batch_num}"
        tasks.append(
            TaskToWrite(
                position=batch_position,
                subject=f"Run batch {batch_num} section subagents",
                status=batch_status,
                description=f"Launch parallel subagents for batch {batch_num} sections ({len(batch_sections)} sections)",
                active_form=f"Running batch {batch_num} subagents",
            )
        )

        # Batch dependencies: batch-1 blocked by create-section-index, batch-N blocked by batch-N-1
        if batch_num == 1:
            dependencies[batch_semantic_id] = ["create-section-index"]
        else:
            dependencies[batch_semantic_id] = [f"batch-{batch_num - 1}"]

        # Create section tasks for this batch
        for section_idx, section_name in enumerate(batch_sections):
            section_position = batch_position + 1 + section_idx
            filename = f"{section_name}.md"

            # Determine section status
            if section_name in completed_sections:
                section_status = TaskStatus.COMPLETED
            elif batch_status == TaskStatus.IN_PROGRESS:
                # All sections in an in_progress batch are in_progress (parallel)
                section_status = TaskStatus.IN_PROGRESS
            else:
                section_status = TaskStatus.PENDING

            tasks.append(
                TaskToWrite(
                    position=section_position,
                    subject=f"Write {filename}",
                    status=section_status,
                    description=f"Write section file: {filename}",
                    active_form=f"Writing {filename}",
                )
            )

            # Section is blocked by its batch task
            section_semantic_id = f"section-{section_position}"
            dependencies[section_semantic_id] = [batch_semantic_id]

    return tasks, dependencies, len(tasks)
