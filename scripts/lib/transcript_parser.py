"""Shared transcript parsing functions for Claude Code JSONL transcripts.

This module provides robust parsing of Claude Code transcript files. It handles
all variations in the JSONL format and is shared between:
- transcript_validator.py (early format validation at setup time)
- write-section-on-stop.py (section-writer frontmatter hook)

Based on analysis of community parsing tools:
- simonw/claude-code-transcripts - Simple, dict-based approach
- daaain/claude-code-log - Content block handling patterns

Key design decisions:
1. No Pydantic overhead (narrow use case: first user msg, last assistant text)
2. Handles both string and array content formats
3. Graceful error handling - never crash on malformed data
4. Debug logging for troubleshooting
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator


def debug_log(msg: str) -> None:
    """Debug logging placeholder - can be enhanced for actual logging."""
    # Intentionally silent by default
    # Enable by setting DEBUG_TRANSCRIPT_PARSER=1
    import os
    if os.environ.get("DEBUG_TRANSCRIPT_PARSER"):
        print(f"[transcript_parser] {msg}")


def read_transcript_entries(transcript_path: str) -> Iterator[dict]:
    """Read and parse JSONL transcript, yielding valid entries.

    Handles:
    - Malformed JSON lines (skipped with warning)
    - Empty lines (skipped)
    - Missing file (raises FileNotFoundError)

    Args:
        transcript_path: Path to the JSONL transcript file

    Yields:
        dict: Parsed JSON entries from the transcript

    Raises:
        FileNotFoundError: If transcript file doesn't exist
    """
    path = Path(transcript_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {transcript_path}")

    for line_num, line in enumerate(path.read_text().strip().split('\n'), 1):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as e:
            # Log but don't fail - transcript may have partial writes
            debug_log(f"Skipping malformed JSON at line {line_num}: {e}")
            continue


def extract_text_from_content(content) -> str:
    """Extract text from content field, handling all formats.

    Formats:
    1. String: "content": "Hello world"
    2. Single text block: "content": [{"type": "text", "text": "Hello"}]
    3. Multiple blocks: "content": [{"type": "text", "text": "A"}, {"type": "text", "text": "B"}]
    4. Mixed blocks: "content": [{"type": "tool_use", ...}, {"type": "text", "text": "C"}]
    5. Empty/null: "content": "" or "content": null or "content": []

    Args:
        content: The content field value (string, list, or None)

    Returns:
        Extracted text, or empty string if no text found
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts)

    return ""


def find_first_user_message(transcript_path: str) -> str:
    """Find the first user message content in the transcript.

    This contains the prompt: "Read /path/to/prompt.md and execute..."

    Args:
        transcript_path: Path to the JSONL transcript file

    Returns:
        The text content of the first user message

    Raises:
        ValueError: If no user message found
        FileNotFoundError: If transcript file doesn't exist
    """
    for entry in read_transcript_entries(transcript_path):
        if entry.get("message", {}).get("role") == "user":
            content = entry["message"].get("content", "")
            text = extract_text_from_content(content)
            if text:
                return text

    raise ValueError("No user message found in transcript")


def find_last_assistant_text_message(transcript_path: str) -> str:
    """Find the last assistant message with text content.

    This is the section content output by the subagent.

    Important: We want the LAST message with TEXT content, not tool_use.
    The subagent may have multiple assistant turns (tool calls, then final output).

    Args:
        transcript_path: Path to the JSONL transcript file

    Returns:
        The text content of the last assistant message

    Raises:
        ValueError: If no assistant text message found
        FileNotFoundError: If transcript file doesn't exist
    """
    last_text = None

    for entry in read_transcript_entries(transcript_path):
        if entry.get("message", {}).get("role") == "assistant":
            content = entry["message"].get("content", "")
            text = extract_text_from_content(content)
            if text:
                last_text = text

    if last_text is None:
        raise ValueError("No assistant text message found in transcript")

    return last_text


def extract_prompt_file_path(user_message: str) -> str:
    """Extract prompt file path from 'Read /path/to/file.md and execute...'

    Args:
        user_message: The user message text containing the prompt path

    Returns:
        The absolute path to the prompt file

    Raises:
        ValueError: If pattern not found or file doesn't end in .md
    """
    # Pattern: "Read /absolute/path/to/file.md and execute"
    match = re.search(r'Read\s+(/[^\s]+\.md)\s+and execute', user_message)
    if match:
        return match.group(1)
    raise ValueError("Could not find prompt file path in user message")


def derive_destination_from_path(prompt_file_path: str) -> tuple[str, str]:
    """Derive sections_dir and filename from prompt file path.

    Path structure:
    - Input:  /path/to/sections/.prompts/section-01-foundation-prompt.md
    - Output: sections_dir = /path/to/sections
              filename = section-01-foundation.md

    The prompt files are always in .prompts/ subdirectory of sections/.
    The filename is the prompt filename with "-prompt" suffix removed.

    Args:
        prompt_file_path: Absolute path to the prompt file

    Returns:
        Tuple of (sections_dir, filename)

    Raises:
        ValueError: If path structure doesn't match expected format
    """
    path = Path(prompt_file_path)

    # Validate expected structure
    if path.parent.name != ".prompts":
        raise ValueError(f"Expected prompt file in .prompts/ directory, got: {path.parent}")

    # sections_dir is parent of .prompts/
    sections_dir = str(path.parent.parent)

    # filename is prompt filename with "-prompt" removed
    stem = path.stem  # "section-01-foundation-prompt"
    if not stem.endswith("-prompt"):
        raise ValueError(f"Expected prompt filename to end with '-prompt', got: {stem}")

    filename = stem.replace("-prompt", "") + ".md"  # "section-01-foundation.md"

    return sections_dir, filename
