"""Validate Claude Code transcript format assumptions.

If Claude Code changes the JSONL schema, this fails fast with clear errors
instead of silently breaking during section writing.

This validator runs during setup-planning-session.py (step 4) to catch
format issues early, before any section writing begins (step 20).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptValidation:
    """Result of validating a transcript file's format."""

    valid: bool
    transcript_path: str
    line_count: int
    user_messages: int
    assistant_messages: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @classmethod
    def success(
        cls,
        transcript_path: str,
        line_count: int,
        user_messages: int,
        assistant_messages: int,
        warnings: tuple[str, ...] = (),
    ) -> Self:
        """Create a successful validation result."""
        return cls(
            valid=True,
            transcript_path=transcript_path,
            line_count=line_count,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            errors=(),
            warnings=warnings,
        )

    @classmethod
    def failure(
        cls,
        transcript_path: str,
        errors: tuple[str, ...],
        line_count: int = 0,
        user_messages: int = 0,
        assistant_messages: int = 0,
        warnings: tuple[str, ...] = (),
    ) -> Self:
        """Create a failed validation result."""
        return cls(
            valid=False,
            transcript_path=transcript_path,
            line_count=line_count,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            errors=errors,
            warnings=warnings,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "transcript_path": self.transcript_path,
            "line_count": self.line_count,
            "user_messages": self.user_messages,
            "assistant_messages": self.assistant_messages,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _validate_content_format(content) -> tuple[bool, str]:
    """Check content is string or array of typed blocks.

    Args:
        content: The content field value to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if isinstance(content, str):
        return True, ""

    if isinstance(content, list):
        for i, block in enumerate(content):
            if not isinstance(block, dict):
                return False, f"content[{i}] is not a dict: {type(block).__name__}"
            if "type" not in block:
                return False, f"content[{i}] missing 'type' field"
        return True, ""

    return False, f"content is neither string nor array: {type(content).__name__}"


def validate_transcript_format(transcript_path: str) -> TranscriptValidation:
    """Validate our parsing assumptions against actual transcript.

    Checks:
    1. File exists and is readable
    2. Each line is valid JSON (or gracefully skippable)
    3. Entries have expected structure: {message: {role, content}}
    4. Content is string OR array of {type, text} blocks
    5. We can find user and assistant messages

    Args:
        transcript_path: Path to the transcript file to validate

    Returns:
        TranscriptValidation with valid=True if all checks pass,
        or valid=False with specific errors describing what failed.
    """
    errors: list[str] = []
    warnings: list[str] = []
    user_count = 0
    assistant_count = 0
    line_count = 0

    path = Path(transcript_path)

    # Check 1: File exists
    if not path.exists():
        return TranscriptValidation.failure(
            transcript_path=transcript_path,
            errors=(f"Transcript not found: {transcript_path}",),
        )

    # Check 2-4: Parse and validate each line
    for line_num, line in enumerate(path.read_text().strip().split('\n'), 1):
        if not line.strip():
            continue
        line_count += 1

        # Check 2: Valid JSON
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            warnings.append(f"Line {line_num}: Malformed JSON (skipped): {e}")
            continue

        # Check 3: Expected structure
        message = entry.get("message")
        if message is None:
            continue  # Progress entries, summaries, etc. - expected

        if not isinstance(message, dict):
            errors.append(f"Line {line_num}: 'message' is not a dict: {type(message).__name__}")
            continue

        role = message.get("role")
        if role not in ("user", "assistant", None):
            warnings.append(f"Line {line_num}: Unexpected role: {role}")

        if role == "user":
            user_count += 1
        elif role == "assistant":
            assistant_count += 1

        # Check 4: Content format
        content = message.get("content")
        if content is not None:
            format_valid, format_error = _validate_content_format(content)
            if not format_valid:
                errors.append(f"Line {line_num}: {format_error}")

    # Check 5: Must have at least some messages
    if line_count == 0:
        errors.append("Transcript is empty")
    elif user_count == 0 and assistant_count == 0:
        errors.append("No user or assistant messages found - format may have changed")

    if errors:
        return TranscriptValidation.failure(
            transcript_path=transcript_path,
            errors=tuple(errors),
            line_count=line_count,
            user_messages=user_count,
            assistant_messages=assistant_count,
            warnings=tuple(warnings),
        )

    return TranscriptValidation.success(
        transcript_path=transcript_path,
        line_count=line_count,
        user_messages=user_count,
        assistant_messages=assistant_count,
        warnings=tuple(warnings),
    )
