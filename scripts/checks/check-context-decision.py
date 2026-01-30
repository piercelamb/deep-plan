#!/usr/bin/env python3
"""Check if context prompts are enabled and return prompt or skip action.

Simple config check - no estimation logic. Returns whether Claude should
prompt the user about compacting before a critical operation.

Usage:
    uv run check-context-decision.py --planning-dir "/path/to/planning" --upcoming-operation "External LLM Review"
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_session_config, ConfigError


def main():
    parser = argparse.ArgumentParser(description="Check if context prompts are enabled")
    parser.add_argument(
        "--planning-dir",
        required=True,
        type=Path,
        help="Path to planning directory (contains deep_plan_config.json)"
    )
    parser.add_argument(
        "--upcoming-operation",
        required=True,
        help="Name of the upcoming operation (e.g., 'External LLM Review')"
    )
    args = parser.parse_args()

    upcoming_operation = args.upcoming_operation

    # Build the prompt with trade-off explanations
    prompt_message = (
        f"Context check before: {upcoming_operation}\n\n"
        "Note: Compaction (manual or auto) may cause workflow instruction loss. "
        "If Claude gets confused after compacting, /clear + re-run /deep-plan is the cleanest recovery - "
        "your progress is preserved in planning files."
    )

    prompt_options = [
        {
            "label": "Continue",
            "description": "Proceed with current context (auto-compact triggers at ~95% if needed)"
        },
        {
            "label": "/clear + re-run",
            "description": "Cleanest recovery if context is critical - fresh window with file-based resume"
        },
    ]

    try:
        config = load_session_config(args.planning_dir)
    except (ConfigError, json.JSONDecodeError) as e:
        # If config can't be loaded, default to prompting
        print(json.dumps({
            "action": "prompt",
            "reason": f"Config error ({e}), defaulting to prompt",
            "check_enabled": True,
            "prompt": {
                "message": prompt_message,
                "options": prompt_options
            }
        }))
        return 0

    ctx = config.get("context", {})
    check_enabled = ctx.get("check_enabled", True)

    # If checks disabled, skip entirely
    if not check_enabled:
        print(json.dumps({
            "action": "skip",
            "reason": "Context prompts disabled in config",
            "check_enabled": False
        }))
        return 0

    # Checks enabled - return prompt
    print(json.dumps({
        "action": "prompt",
        "reason": "Context prompts enabled",
        "check_enabled": True,
        "prompt": {
            "message": prompt_message,
            "options": prompt_options
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
