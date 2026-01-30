#!/usr/bin/env python3
"""Write section files from section-writer subagent output.

This SubagentStop hook is defined in hooks/hooks.json with a matcher for
"deep-plan:section-writer". It runs only when section-writer subagents complete.

Note: Originally planned as a frontmatter Stop hook, but plugin frontmatter hooks
don't execute due to Claude Code bug #17688. Using hooks.json with matcher as workaround.

Architecture:
1. Reads agent_transcript_path from SubagentStop payload
2. Extracts first user message to get prompt file path
3. Derives sections_dir and filename from prompt path structure
4. Extracts last assistant text message as raw markdown content
5. Writes content to sections_dir/filename

This replaces the old two-hook system (SubagentStart + SubagentStop) that:
- Required tracking files for agent identification
- Required JSON output from the subagent
- Had complex JSON parsing with multiple fallback stages
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Debug log file
DEBUG_LOG = Path.home() / ".claude" / "write-section-on-stop-debug.log"


def debug_log(msg: str) -> None:
    """Append debug message to log file."""
    if not os.environ.get("DEBUG_SECTION_WRITER_HOOK"):
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except OSError:
        pass


# Add parent directories to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from lib.transcript_parser import (
        extract_prompt_file_path,
        derive_destination_from_path,
        find_first_user_message,
        find_last_assistant_text_message,
    )
    debug_log("Successfully imported transcript_parser")
except ImportError as e:
    debug_log(f"Failed to import transcript_parser: {e}")
    raise


def main() -> int:
    """Process Stop hook payload and write section file.

    Returns:
        0 always (hooks should not fail the session)
    """
    debug_log("=== HOOK STARTED ===")
    debug_log(f"cwd = {os.getcwd()}")

    # 1. Parse stdin payload
    try:
        raw_input = sys.stdin.read()
        debug_log(f"Raw stdin: {raw_input[:500]}")
        payload = json.loads(raw_input) if raw_input else {}
    except json.JSONDecodeError as e:
        debug_log(f"Failed to parse stdin: {e}")
        return 0
    except Exception as e:
        debug_log(f"Error reading stdin: {e}")
        return 0

    # 2. Get transcript path
    transcript_path = payload.get("agent_transcript_path")
    debug_log(f"agent_transcript_path = {transcript_path}")
    if not transcript_path:
        debug_log("No agent_transcript_path, exiting")
        return 0

    # 3. Extract prompt file path from first user message
    try:
        first_user_msg = find_first_user_message(transcript_path)
        debug_log(f"First user message: {first_user_msg[:200]}...")
    except (FileNotFoundError, ValueError) as e:
        debug_log(f"Failed to get first user message: {e}")
        return 0

    try:
        prompt_file_path = extract_prompt_file_path(first_user_msg)
        debug_log(f"Prompt file path: {prompt_file_path}")
    except ValueError as e:
        debug_log(f"Failed to extract prompt file path: {e}")
        return 0

    # 4. Derive destination from prompt path
    try:
        sections_dir, filename = derive_destination_from_path(prompt_file_path)
        debug_log(f"sections_dir = {sections_dir}, filename = {filename}")
    except ValueError as e:
        debug_log(f"Failed to derive destination: {e}")
        return 0

    # 5. Extract section content from last assistant message
    try:
        content = find_last_assistant_text_message(transcript_path)
        debug_log(f"Content length: {len(content)} bytes")
    except (FileNotFoundError, ValueError) as e:
        debug_log(f"Failed to get assistant content: {e}")
        return 0

    # 6. Write to destination
    sections_path = Path(sections_dir)
    if not sections_path.exists():
        debug_log(f"sections_dir does not exist: {sections_dir}")
        return 0

    output_path = sections_path / filename
    try:
        output_path.write_text(content)
        debug_log(f"Wrote {len(content)} bytes to {output_path}")

        # Verify write
        if output_path.exists():
            actual_size = output_path.stat().st_size
            debug_log(f"VERIFIED: File exists with {actual_size} bytes")
        else:
            debug_log("FAILED: File does not exist after write!")
    except OSError as e:
        debug_log(f"Failed to write file: {e}")
        return 0

    debug_log("=== HOOK FINISHED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
