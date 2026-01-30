"""Tests for transcript_validator.py - transcript format validation."""

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib.transcript_validator import (
    TranscriptValidation,
    validate_transcript_format,
)


class TestValidateTranscriptFormat:
    """Tests for validate_transcript_format()"""

    def test_valid_transcript_string_content(self, tmp_path):
        """Should validate transcript with string content."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "user", "content": "Hello"}}),
            json.dumps({"message": {"role": "assistant", "content": "Hi there"}}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is True
        assert result.user_messages == 1
        assert result.assistant_messages == 1
        assert result.errors == ()

    def test_valid_transcript_array_content(self, tmp_path):
        """Should validate transcript with array content blocks."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "user", "content": [
                {"type": "text", "text": "Hello"}
            ]}}),
            json.dumps({"message": {"role": "assistant", "content": [
                {"type": "text", "text": "Hi"},
                {"type": "tool_use", "id": "123", "name": "Read", "input": {}}
            ]}}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is True
        assert result.errors == ()

    def test_skips_progress_entries(self, tmp_path):
        """Should skip entries without message field (progress, etc.)."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"type": "progress", "data": {}}),
            json.dumps({"message": {"role": "user", "content": "Hello"}}),
            json.dumps({"type": "summary", "summary": "Test"}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is True
        assert result.line_count == 3
        assert result.user_messages == 1

    def test_warns_on_malformed_json(self, tmp_path):
        """Should warn but not fail on malformed JSON lines."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "user", "content": "Hello"}}),
            "not valid json",
            json.dumps({"message": {"role": "assistant", "content": "Hi"}}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is True  # Warnings don't fail
        assert len(result.warnings) == 1
        assert "Malformed JSON" in result.warnings[0]

    def test_error_on_missing_file(self):
        """Should error if transcript file doesn't exist."""
        result = validate_transcript_format("/nonexistent/path.jsonl")

        assert result.valid is False
        assert "not found" in result.errors[0]

    def test_error_on_empty_transcript(self, tmp_path):
        """Should error if transcript is empty."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("")

        result = validate_transcript_format(str(transcript))

        assert result.valid is False
        assert "empty" in result.errors[0].lower()

    def test_error_on_no_messages(self, tmp_path):
        """Should error if no user/assistant messages found."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"type": "progress", "data": {}}),
            json.dumps({"type": "summary", "summary": "Test"}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is False
        assert "No user or assistant messages" in result.errors[0]

    def test_error_on_invalid_content_format(self, tmp_path):
        """Should error if content is neither string nor array."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "user", "content": 12345}}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is False
        assert "neither string nor array" in result.errors[0]

    def test_error_on_array_block_missing_type(self, tmp_path):
        """Should error if content block is missing 'type' field."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "user", "content": [
                {"text": "Hello"}  # Missing "type" field
            ]}}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is False
        assert "missing 'type'" in result.errors[0]

    def test_error_on_message_not_dict(self, tmp_path):
        """Should error if 'message' field is not a dict."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": "not a dict"}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))

        assert result.valid is False
        assert "'message' is not a dict" in result.errors[0]

    def test_to_dict_method(self, tmp_path):
        """Should serialize to dictionary correctly."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "user", "content": "Hello"}}),
        ]
        transcript.write_text("\n".join(lines))

        result = validate_transcript_format(str(transcript))
        as_dict = result.to_dict()

        assert as_dict["valid"] is True
        assert as_dict["user_messages"] == 1
        assert isinstance(as_dict["errors"], list)
        assert isinstance(as_dict["warnings"], list)


class TestTranscriptValidationDataclass:
    """Tests for TranscriptValidation dataclass methods."""

    def test_success_factory(self):
        """Should create successful validation."""
        result = TranscriptValidation.success(
            transcript_path="/path/to/file.jsonl",
            line_count=10,
            user_messages=3,
            assistant_messages=4,
        )
        assert result.valid is True
        assert result.errors == ()
        assert result.line_count == 10

    def test_failure_factory(self):
        """Should create failed validation."""
        result = TranscriptValidation.failure(
            transcript_path="/path/to/file.jsonl",
            errors=("Error 1", "Error 2"),
        )
        assert result.valid is False
        assert len(result.errors) == 2
        assert result.line_count == 0

    def test_success_with_warnings(self):
        """Should handle warnings in successful validation."""
        result = TranscriptValidation.success(
            transcript_path="/path/to/file.jsonl",
            line_count=10,
            user_messages=3,
            assistant_messages=4,
            warnings=("Warning 1",),
        )
        assert result.valid is True
        assert len(result.warnings) == 1
