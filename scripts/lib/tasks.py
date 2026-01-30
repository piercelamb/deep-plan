"""Task definitions and generation for deep-plan workflow.

Replaces the legacy TodoWrite system with Claude Code Tasks (v2.1.16+).
Provides native dependency tracking, persistence, and subagent visibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class TaskStatus(StrEnum):
    """Status values for tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskDefinition:
    """Definition of a workflow task."""

    subject: str
    description: str
    active_form: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        return {
            "subject": self.subject,
            "description": self.description,
            "activeForm": self.active_form,
        }


# Maximum concurrent subagents supported by Claude Code
BATCH_SIZE = 7

# Task IDs mapped to workflow step numbers
# Steps 0-4 are setup (not tracked as tasks)
# Steps 6-22 are the main workflow
TASK_IDS: dict[int, str] = {
    6: "research-decision",
    7: "execute-research",
    8: "detailed-interview",
    9: "save-interview",
    10: "write-spec",
    11: "generate-plan",
    12: "context-check-pre-review",
    13: "external-review",
    14: "integrate-feedback",
    15: "user-review",
    16: "apply-tdd",
    17: "context-check-pre-split",
    18: "create-section-index",
    19: "generate-section-tasks",
    20: "write-sections",
    21: "final-verification",
    22: "output-summary",
}

# Reverse mapping for lookup
TASK_ID_TO_STEP: dict[str, int] = {v: k for k, v in TASK_IDS.items()}

# Step names for display
STEP_NAMES: dict[int, str] = {
    0: "Context check",
    1: "Print intro and validate environment",
    2: "Handle environment errors",
    3: "Validate spec file input",
    4: "Setup planning session",
    6: "Research decision",
    7: "Execute research",
    8: "Detailed interview",
    9: "Save interview transcript",
    10: "Write initial spec",
    11: "Generate implementation plan",
    12: "Context check (pre-review)",
    13: "External LLM review",
    14: "Integrate external feedback",
    15: "User review of integrated plan",
    16: "Apply TDD approach",
    17: "Context check (pre-split)",
    18: "Create section index",
    19: "Generate section tasks",
    20: "Write section files",
    21: "Final status and cleanup",
    22: "Output summary",
}

# Explicit dependency graph (replaces step ordering)
# Each task lists the task IDs it is blocked by
TASK_DEPENDENCIES: dict[str, list[str]] = {
    # Context items - each blocked by final step, stays visible throughout workflow
    # Values are stored in subject field for visibility after compaction
    "context-plugin-root": ["output-summary"],
    "context-planning-dir": ["output-summary"],
    "context-initial-file": ["output-summary"],
    "context-review-mode": ["output-summary"],
    # Main workflow
    "research-decision": [],  # Can start immediately
    "execute-research": ["research-decision"],
    "detailed-interview": ["execute-research"],  # Depends on research (even if skipped)
    "save-interview": ["detailed-interview"],
    "write-spec": ["save-interview"],
    "generate-plan": ["write-spec"],
    "context-check-pre-review": ["generate-plan"],
    "external-review": ["context-check-pre-review"],
    "integrate-feedback": ["external-review"],
    "user-review": ["integrate-feedback"],
    "apply-tdd": ["user-review"],
    "context-check-pre-split": ["apply-tdd"],
    "create-section-index": ["context-check-pre-split"],
    "generate-section-tasks": ["create-section-index"],
    "write-sections": ["generate-section-tasks"],
    "final-verification": ["write-sections"],
    "output-summary": ["final-verification"],
}

# Task definitions with subject, description, and activeForm
# Note: Context tasks are NOT in this dict - they're generated dynamically
# with values in the subject field by create_context_tasks()
TASK_DEFINITIONS: dict[str, TaskDefinition] = {
    "research-decision": TaskDefinition(
        subject="Research Decision",
        description="Read research-protocol.md and decide on research approach",
        active_form="Deciding on research approach",
    ),
    "execute-research": TaskDefinition(
        subject="Execute Research",
        description="Launch research subagents based on decisions from previous step",
        active_form="Executing research",
    ),
    "detailed-interview": TaskDefinition(
        subject="Detailed Interview",
        description="Read interview-protocol.md and conduct stakeholder interview",
        active_form="Conducting detailed interview",
    ),
    "save-interview": TaskDefinition(
        subject="Save Interview Transcript",
        description="Write Q&A to claude-interview.md",
        active_form="Saving interview transcript",
    ),
    "write-spec": TaskDefinition(
        subject="Write Initial Spec",
        description="Combine input, research, and interview into claude-spec.md",
        active_form="Writing initial spec",
    ),
    "generate-plan": TaskDefinition(
        subject="Generate Implementation Plan",
        description="Create detailed plan in claude-plan.md. Write for unfamiliar reader.",
        active_form="Generating implementation plan",
    ),
    "context-check-pre-review": TaskDefinition(
        subject="Context Check (Pre-Review)",
        description="Run check-context-decision.py before external review",
        active_form="Checking context (pre-review)",
    ),
    "external-review": TaskDefinition(
        subject="External LLM Review",
        description="Read external-review.md and run review based on review_mode",
        active_form="Running external LLM review",
    ),
    "integrate-feedback": TaskDefinition(
        subject="Integrate External Feedback",
        description="Write integration notes and update claude-plan.md",
        active_form="Integrating external feedback",
    ),
    "user-review": TaskDefinition(
        subject="User Review of Integrated Plan",
        description="Wait for user to review and approve claude-plan.md",
        active_form="Waiting for user review",
    ),
    "apply-tdd": TaskDefinition(
        subject="Apply TDD Approach",
        description="Read tdd-approach.md and create claude-plan-tdd.md",
        active_form="Applying TDD approach",
    ),
    "context-check-pre-split": TaskDefinition(
        subject="Context Check (Pre-Split)",
        description="Run check-context-decision.py before section splitting",
        active_form="Checking context (pre-split)",
    ),
    "create-section-index": TaskDefinition(
        subject="Create Section Index",
        description="Read section-index.md and create sections/index.md with SECTION_MANIFEST",
        active_form="Creating section index",
    ),
    "generate-section-tasks": TaskDefinition(
        subject="Generate Section Tasks",
        description="Run generate-section-tasks.py to get batch task operations",
        active_form="Generating section tasks",
    ),
    "write-sections": TaskDefinition(
        subject="Write Section Files",
        description="Read section-splitting.md and execute batch loop with subagents",
        active_form="Writing section files",
    ),
    "final-verification": TaskDefinition(
        subject="Final Verification",
        description="Run check-sections.py to verify all sections complete",
        active_form="Running final verification",
    ),
    "output-summary": TaskDefinition(
        subject="Output Summary",
        description="Print generated files and next steps",
        active_form="Outputting summary",
    ),
}


def create_context_tasks(
    plugin_root: str,
    planning_dir: str,
    initial_file: str,
    review_mode: str,
) -> list[dict]:
    """Create individual context tasks with values in subject field.

    Each context item becomes its own task:
    - Subject contains the key=value (visible in task list after compaction)
    - All blocked by output-summary (stay pending until workflow ends)

    Args:
        plugin_root: Path to plugin root directory
        planning_dir: Path to planning directory
        initial_file: Path to initial spec file
        review_mode: How plan review is performed (external_llm, opus_subagent, skip)

    Returns:
        List of task dicts ready for TaskCreate
    """
    context_items = [
        ("context-plugin-root", f"plugin_root={plugin_root}"),
        ("context-planning-dir", f"planning_dir={planning_dir}"),
        ("context-initial-file", f"initial_file={initial_file}"),
        ("context-review-mode", f"review_mode={review_mode}"),
    ]

    return [
        {
            "id": task_id,
            "subject": value,  # VALUE is in subject for visibility
            "description": "Session context item",
            "activeForm": "Context",
            "status": TaskStatus.PENDING,
            "blockedBy": TASK_DEPENDENCIES[task_id],
        }
        for task_id, value in context_items
    ]


def generate_expected_tasks(
    resume_step: int,
    plugin_root: str,
    planning_dir: str,
    initial_file: str,
    review_mode: str,
) -> list[dict]:
    """Generate expected task states based on file state.

    Returns list of task dicts for ALL workflow tasks. Status is derived
    from the resume_step (which is inferred from file existence):
    - Steps < resume_step -> "completed"
    - Step == resume_step -> "in_progress"
    - Steps > resume_step -> "pending"

    Claude compares these expected tasks against TaskList and reconciles:
    - Task doesn't exist -> TaskCreate
    - Task exists but wrong status -> TaskUpdate
    - Task exists with correct status -> no action

    Args:
        resume_step: The step we're resuming from (or 6 for fresh start)
        plugin_root: Path to plugin root directory
        planning_dir: Path to planning directory
        initial_file: Path to initial spec file
        review_mode: How plan review is performed

    Returns:
        List of task dicts with id, subject, description, activeForm, status, blockedBy
    """
    expected: list[dict] = []

    # Add context tasks first (always pending until workflow ends)
    # Each context item is a separate task with VALUE in subject for visibility
    expected.extend(
        create_context_tasks(
            plugin_root=plugin_root,
            planning_dir=planning_dir,
            initial_file=initial_file,
            review_mode=review_mode,
        )
    )

    # Add workflow tasks
    for step_num, task_id in sorted(TASK_IDS.items()):
        task_def = TASK_DEFINITIONS[task_id]

        # Determine status based on resume_step
        if step_num < resume_step:
            status = TaskStatus.COMPLETED
        elif step_num == resume_step:
            status = TaskStatus.IN_PROGRESS
        else:
            status = TaskStatus.PENDING

        expected.append({
            "id": task_id,
            "subject": task_def.subject,
            "description": task_def.description,
            "activeForm": task_def.active_form,
            "status": status,
            "blockedBy": TASK_DEPENDENCIES[task_id],
        })

    return expected
