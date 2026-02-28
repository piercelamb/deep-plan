#!/usr/bin/env python3
"""Capture session_id and plugin_root, expose via Claude's context.

This hook reads session_id from the JSON payload on stdin and:
1. Outputs it to stdout as additionalContext (Claude sees this directly)
2. Also captures CLAUDE_PLUGIN_ROOT as DEEP_PLUGIN_ROOT (for SKILL.md path resolution)
3. Optionally writes to CLAUDE_ENV_FILE if available (fallback for bash)

The additionalContext approach is primary because:
- CLAUDE_ENV_FILE is unreliable (empty string bug, not sourced on resume)
- After /clear, env var has OLD session_id while hook gets NEW one
- additionalContext bypasses these issues by flowing through Claude's context
- CLAUDE_PLUGIN_ROOT is only available in hooks.json, not in SKILL.md files

Usage:
    This script is called automatically by Claude Code when configured
    as a SessionStart hook in hooks/hooks.json (for plugins):

    {
      "hooks": {
        "SessionStart": [
          {
            "hooks": [
              {
                "type": "command",
                "command": "uv run ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/capture-session-id.py"
              }
            ]
          }
        ]
      }
    }
"""

import json
import os
import sys


def main() -> int:
    """Capture session_id, output to Claude's context and optionally CLAUDE_ENV_FILE.

    Returns:
        0 always (hooks should not fail the session start)
    """
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No valid JSON on stdin - silently succeed
        return 0
    except Exception:
        # Any other error reading stdin - silently succeed
        return 0

    session_id = payload.get("session_id")
    transcript_path = payload.get("transcript_path")

    # Capture CLAUDE_PLUGIN_ROOT (available because hooks.json expands it)
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")

    # Need at least session_id to proceed
    if not session_id:
        return 0

    # Build additionalContext lines
    context_parts = []

    existing_session_id = os.environ.get("DEEP_SESSION_ID")
    if existing_session_id != session_id:
        context_parts.append(f"DEEP_SESSION_ID={session_id}")

    if plugin_root:
        context_parts.append(f"DEEP_PLUGIN_ROOT={plugin_root}")

    if context_parts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }
        print(json.dumps(output))

    # SECONDARY: Also try CLAUDE_ENV_FILE for bash commands (may not work)
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            # Check if already set (avoid duplicates from multiple plugins)
            existing_content = ""
            try:
                with open(env_file) as f:
                    existing_content = f.read()
            except FileNotFoundError:
                pass

            # Only write if not already present
            lines_to_write = []
            if f"DEEP_SESSION_ID={session_id}" not in existing_content:
                lines_to_write.append(f"export DEEP_SESSION_ID={session_id}\n")
            if (
                transcript_path
                and f"CLAUDE_TRANSCRIPT_PATH={transcript_path}" not in existing_content
            ):
                lines_to_write.append(
                    f"export CLAUDE_TRANSCRIPT_PATH={transcript_path}\n"
                )

            if lines_to_write:
                with open(env_file, "a") as f:
                    f.writelines(lines_to_write)
        except OSError:
            # Failed to read/write - silently succeed (we already output to context)
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
