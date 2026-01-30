"""Tests for transcript_parser.py - shared transcript parsing functions."""

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib.transcript_parser import (
    read_transcript_entries,
    extract_text_from_content,
    find_first_user_message,
    find_last_assistant_text_message,
    extract_prompt_file_path,
    derive_destination_from_path,
)


class TestReadTranscriptEntries:
    """Tests for read_transcript_entries()"""

    def test_reads_valid_jsonl(self, tmp_path):
        """Should yield all valid JSON entries."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"a": 1}\n{"b": 2}\n{"c": 3}\n')

        entries = list(read_transcript_entries(str(transcript)))
        assert len(entries) == 3
        assert entries[0] == {"a": 1}

    def test_skips_malformed_lines(self, tmp_path):
        """Should skip malformed JSON and continue."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"a": 1}\nnot json\n{"b": 2}\n')

        entries = list(read_transcript_entries(str(transcript)))
        assert len(entries) == 2

    def test_skips_empty_lines(self, tmp_path):
        """Should skip empty lines."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"a": 1}\n\n\n{"b": 2}\n')

        entries = list(read_transcript_entries(str(transcript)))
        assert len(entries) == 2

    def test_raises_on_missing_file(self):
        """Should raise FileNotFoundError for missing transcript."""
        with pytest.raises(FileNotFoundError):
            list(read_transcript_entries("/nonexistent/path.jsonl"))

    def test_handles_empty_file(self, tmp_path):
        """Should return empty iterator for empty file."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("")

        entries = list(read_transcript_entries(str(transcript)))
        assert len(entries) == 0


class TestFindFirstUserMessage:
    """Tests for find_first_user_message()"""

    def test_finds_user_message_string_content(self, tmp_path):
        """Should find user message with string content."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({
            "message": {"role": "user", "content": "Read /path/to/prompt.md and execute"}
        }))

        result = find_first_user_message(str(transcript))
        assert "Read /path/to/prompt.md" in result

    def test_finds_user_message_list_content(self, tmp_path):
        """Should find user message with list content blocks."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "Read /path/to/prompt.md and execute"}]
            }
        }))

        result = find_first_user_message(str(transcript))
        assert "Read /path/to/prompt.md" in result

    def test_skips_non_user_entries(self, tmp_path):
        """Should skip progress and assistant entries."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"type": "progress", "data": {}}),
            json.dumps({"message": {"role": "assistant", "content": "Hi"}}),
            json.dumps({"message": {"role": "user", "content": "The real prompt"}}),
        ]
        transcript.write_text("\n".join(lines))

        result = find_first_user_message(str(transcript))
        assert result == "The real prompt"

    def test_skips_user_entries_without_message(self, tmp_path):
        """Should skip entries that have type but no message field."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"type": "user", "data": "no message field"}),
            json.dumps({"message": {"role": "user", "content": "Has message field"}}),
        ]
        transcript.write_text("\n".join(lines))

        result = find_first_user_message(str(transcript))
        assert result == "Has message field"

    def test_raises_when_no_user_message(self, tmp_path):
        """Should raise ValueError if no user message found."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({
            "message": {"role": "assistant", "content": "Only assistant"}
        }))

        with pytest.raises(ValueError, match="No user message found"):
            find_first_user_message(str(transcript))


class TestFindLastAssistantTextMessage:
    """Tests for find_last_assistant_text_message()"""

    def test_finds_last_of_multiple_assistant_messages(self, tmp_path):
        """Should return the LAST assistant text message."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "First response"}}),
            json.dumps({"message": {"role": "user", "content": "Follow up"}}),
            json.dumps({"message": {"role": "assistant", "content": "Second response"}}),
            json.dumps({"message": {"role": "assistant", "content": "Final response"}}),
        ]
        transcript.write_text("\n".join(lines))

        result = find_last_assistant_text_message(str(transcript))
        assert result == "Final response"

    def test_skips_tool_use_only_messages(self, tmp_path):
        """Should skip assistant messages that only have tool_use blocks."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "Text before tools"}}),
            json.dumps({"message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "123", "name": "Read", "input": {}}
            ]}}),
        ]
        transcript.write_text("\n".join(lines))

        result = find_last_assistant_text_message(str(transcript))
        assert result == "Text before tools"

    def test_extracts_text_from_mixed_blocks(self, tmp_path):
        """Should extract text blocks even when mixed with tool_use."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Here's what I found:"},
                    {"type": "tool_use", "id": "123", "name": "Read", "input": {}},
                    {"type": "text", "text": "And here's more."}
                ]
            }
        }))

        result = find_last_assistant_text_message(str(transcript))
        assert "Here's what I found:" in result
        assert "And here's more." in result

    def test_handles_real_world_transcript_format(self, tmp_path):
        """Should handle actual Claude Code transcript format."""
        # This mirrors the actual format observed in transcripts
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "parentUuid": None,
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "Read /path/to/prompt.md and execute"
                },
                "uuid": "abc123",
                "timestamp": "2026-01-27T12:00:00Z"
            }),
            json.dumps({
                "parentUuid": "abc123",
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-5-20251101",
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "tool1", "name": "Read", "input": {"file_path": "/path"}}
                    ]
                },
                "uuid": "def456"
            }),
            json.dumps({
                "parentUuid": "def456",
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "tool1", "content": "file content"}]
                }
            }),
            json.dumps({
                "parentUuid": "ghi789",
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "# Section 01: Foundation\n\nThis is the section content."}
                    ]
                }
            }),
        ]
        transcript.write_text("\n".join(lines))

        result = find_last_assistant_text_message(str(transcript))
        assert "# Section 01: Foundation" in result
        assert "This is the section content." in result

    def test_raises_when_no_assistant_text(self, tmp_path):
        """Should raise ValueError if no assistant text message found."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({
            "message": {"role": "user", "content": "Only user message"}
        }))

        with pytest.raises(ValueError, match="No assistant text message found"):
            find_last_assistant_text_message(str(transcript))


class TestExtractTextFromContent:
    """Tests for extract_text_from_content()"""

    def test_handles_string_content(self):
        """Should return string content as-is."""
        assert extract_text_from_content("Hello world") == "Hello world"

    def test_handles_none(self):
        """Should return empty string for None."""
        assert extract_text_from_content(None) == ""

    def test_handles_empty_string(self):
        """Should return empty string for empty string."""
        assert extract_text_from_content("") == ""

    def test_handles_empty_list(self):
        """Should return empty string for empty list."""
        assert extract_text_from_content([]) == ""

    def test_handles_single_text_block(self):
        """Should extract text from single text block."""
        content = [{"type": "text", "text": "Hello"}]
        assert extract_text_from_content(content) == "Hello"

    def test_handles_multiple_text_blocks(self):
        """Should join multiple text blocks with newlines."""
        content = [
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"}
        ]
        assert extract_text_from_content(content) == "Line 1\nLine 2"

    def test_filters_out_tool_use_blocks(self):
        """Should ignore tool_use blocks."""
        content = [
            {"type": "text", "text": "Before"},
            {"type": "tool_use", "id": "123", "name": "Read"},
            {"type": "text", "text": "After"}
        ]
        assert extract_text_from_content(content) == "Before\nAfter"

    def test_handles_text_block_with_empty_text(self):
        """Should skip text blocks with empty text."""
        content = [
            {"type": "text", "text": "Real text"},
            {"type": "text", "text": ""},
            {"type": "text", "text": "More text"}
        ]
        assert extract_text_from_content(content) == "Real text\nMore text"

    def test_handles_malformed_blocks(self):
        """Should skip blocks without proper structure."""
        content = [
            {"type": "text", "text": "Valid"},
            {"type": "text"},  # Missing text field
            {"wrong": "structure"},
            {"type": "text", "text": "Also valid"}
        ]
        assert extract_text_from_content(content) == "Valid\nAlso valid"

    def test_handles_non_dict_list_items(self):
        """Should skip non-dict items in list."""
        content = [
            {"type": "text", "text": "Valid"},
            "just a string",
            123,
            None,
            {"type": "text", "text": "Also valid"}
        ]
        assert extract_text_from_content(content) == "Valid\nAlso valid"


class TestExtractPromptFilePath:
    """Tests for extract_prompt_file_path()"""

    def test_extracts_absolute_path(self):
        """Should extract absolute path from standard prompt format."""
        msg = "Read /Users/foo/planning/sections/.prompts/section-01-prompt.md and execute the instructions."
        result = extract_prompt_file_path(msg)
        assert result == "/Users/foo/planning/sections/.prompts/section-01-prompt.md"

    def test_handles_path_with_hyphens_in_parent_dirs(self):
        """Should handle paths where parent dirs have hyphens."""
        msg = "Read /Users/foo/My-Projects/planning/sections/.prompts/section-01-prompt.md and execute"
        result = extract_prompt_file_path(msg)
        assert "section-01-prompt.md" in result

    def test_handles_different_section_names(self):
        """Should work with various section names."""
        test_cases = [
            "section-01-foundation-prompt.md",
            "section-10-integration-prompt.md",
            "section-99-final-prompt.md",
        ]
        for filename in test_cases:
            msg = f"Read /path/to/.prompts/{filename} and execute the instructions."
            result = extract_prompt_file_path(msg)
            assert filename in result

    def test_raises_on_no_match(self):
        """Should raise ValueError when pattern not found."""
        with pytest.raises(ValueError, match="Could not find prompt file path"):
            extract_prompt_file_path("This message has no prompt path")

    def test_raises_on_wrong_extension(self):
        """Should raise if file doesn't end in .md."""
        with pytest.raises(ValueError):
            extract_prompt_file_path("Read /path/to/file.txt and execute")


class TestDeriveDestinationFromPromptPath:
    """Tests for deriving sections_dir and filename from prompt file path."""

    def test_derives_from_standard_path(self):
        """Should derive destination from standard prompt path structure."""
        prompt_path = "/Users/foo/planning/sections/.prompts/section-01-foundation-prompt.md"
        sections_dir, filename = derive_destination_from_path(prompt_path)

        assert sections_dir == "/Users/foo/planning/sections"
        assert filename == "section-01-foundation.md"

    def test_handles_various_section_names(self):
        """Should handle different section naming patterns."""
        test_cases = [
            ("section-01-foundation-prompt.md", "section-01-foundation.md"),
            ("section-10-integration-prompt.md", "section-10-integration.md"),
            ("section-05-api-clients-prompt.md", "section-05-api-clients.md"),
        ]
        for prompt_name, expected_filename in test_cases:
            prompt_path = f"/path/to/sections/.prompts/{prompt_name}"
            _, filename = derive_destination_from_path(prompt_path)
            assert filename == expected_filename

    def test_handles_deeply_nested_paths(self):
        """Should work with deeply nested planning directories."""
        prompt_path = "/Users/foo/projects/my-app/planning/feature-x/sections/.prompts/section-01-prompt.md"
        sections_dir, _ = derive_destination_from_path(prompt_path)

        assert sections_dir == "/Users/foo/projects/my-app/planning/feature-x/sections"

    def test_raises_if_not_in_prompts_dir(self):
        """Should raise if prompt is not in .prompts/ directory."""
        prompt_path = "/Users/foo/planning/sections/section-01-prompt.md"
        with pytest.raises(ValueError, match=".prompts/ directory"):
            derive_destination_from_path(prompt_path)

    def test_raises_if_not_prompt_suffix(self):
        """Should raise if filename doesn't end with -prompt."""
        prompt_path = "/Users/foo/planning/sections/.prompts/section-01-foundation.md"
        with pytest.raises(ValueError, match="-prompt"):
            derive_destination_from_path(prompt_path)
