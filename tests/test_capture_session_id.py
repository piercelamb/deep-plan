"""Tests for the SessionStart hook that captures session_id.

Tests for scripts/hooks/capture-session-id.py

The hook outputs session_id via additionalContext (primary) and also writes
to CLAUDE_ENV_FILE (secondary fallback for bash commands).
"""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path for importing the hook
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "hooks"))
from importlib import import_module


@pytest.fixture
def hook_module():
    """Import the hook module fresh for each test."""
    # Need to import as module since filename has hyphens
    spec = __import__("importlib.util").util.spec_from_file_location(
        "capture_session_id",
        Path(__file__).parent.parent / "scripts" / "hooks" / "capture-session-id.py"
    )
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCaptureSessionIdHook:
    """Test capture-session-id.py hook."""

    def test_outputs_session_id_as_additional_context(self, hook_module, capsys):
        """Valid session_id -> outputs hookSpecificOutput with additionalContext."""
        payload = {"session_id": "test-session-123"}

        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "DEEP_PLAN_SESSION_ID=test-session-123",
            }
        }

    def test_succeeds_when_claude_env_file_not_set(self, hook_module, capsys):
        """Should succeed and output additionalContext even when CLAUDE_ENV_FILE is not set."""
        payload = {"session_id": "test-session-222"}

        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "DEEP_PLAN_SESSION_ID=test-session-222" in captured.out

    def test_succeeds_when_claude_env_file_empty_string(self, hook_module, capsys):
        """Should succeed when CLAUDE_ENV_FILE is empty string (bug in Claude Code)."""
        payload = {"session_id": "test-session-333"}

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": ""}, clear=True):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "DEEP_PLAN_SESSION_ID=test-session-333" in captured.out

    def test_valid_payload_writes_to_env_file(self, tmp_path, hook_module, capsys):
        """Valid JSON with session_id -> writes to CLAUDE_ENV_FILE (secondary)."""
        env_file = tmp_path / "env"
        payload = {"session_id": "abc-123-def"}

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        # Primary: additionalContext output
        captured = capsys.readouterr()
        assert "DEEP_PLAN_SESSION_ID=abc-123-def" in captured.out
        # Secondary: env file
        content = env_file.read_text()
        assert "export CLAUDE_SESSION_ID=abc-123-def" in content

    def test_invalid_json_succeeds_silently(self, hook_module, capsys):
        """Invalid JSON -> returns 0, no crash, no output."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin", StringIO("not json")):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""  # No output for invalid JSON

    def test_empty_stdin_succeeds_silently(self, hook_module, capsys):
        """Empty stdin -> returns 0, no crash, no output."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin", StringIO("")):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_missing_session_id_succeeds_silently(self, hook_module, capsys):
        """JSON without session_id -> returns 0, no output."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin", StringIO('{"other": "data"}')):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_appends_to_existing_env_file(self, tmp_path, hook_module):
        """Appends to existing env file, doesn't overwrite."""
        env_file = tmp_path / "env"
        env_file.write_text("export EXISTING_VAR=value\n")

        payload = {"session_id": "new-session"}

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        content = env_file.read_text()
        assert "EXISTING_VAR=value" in content
        assert "CLAUDE_SESSION_ID=new-session" in content

    def test_session_id_with_special_characters(self, tmp_path, hook_module, capsys):
        """Session ID with UUID format outputs correctly."""
        env_file = tmp_path / "env"
        payload = {"session_id": "550e8400-e29b-41d4-a716-446655440000"}

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        # Check additionalContext output
        captured = capsys.readouterr()
        assert "DEEP_PLAN_SESSION_ID=550e8400-e29b-41d4-a716-446655440000" in captured.out
        # Check env file
        content = env_file.read_text()
        assert "CLAUDE_SESSION_ID=550e8400-e29b-41d4-a716-446655440000" in content

    def test_payload_with_extra_fields(self, tmp_path, hook_module, capsys):
        """Payload with extra fields still extracts session_id."""
        env_file = tmp_path / "env"
        payload = {
            "session_id": "my-session",
            "timestamp": "2026-01-26T12:00:00Z",
            "source": "clear",
            "other_field": {"nested": "value"},
        }

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "DEEP_PLAN_SESSION_ID=my-session" in captured.out
        content = env_file.read_text()
        assert "CLAUDE_SESSION_ID=my-session" in content

    def test_env_file_write_error_still_outputs_context(self, tmp_path, hook_module, capsys):
        """Write error -> still outputs additionalContext, returns 0."""
        # Point to a directory (can't write to it as a file)
        env_file = tmp_path / "subdir"
        env_file.mkdir()

        payload = {"session_id": "my-session"}

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        # Should succeed and output additionalContext even though env file write failed
        assert result == 0
        captured = capsys.readouterr()
        assert "DEEP_PLAN_SESSION_ID=my-session" in captured.out

    def test_skips_duplicate_session_id(self, tmp_path, hook_module):
        """If session_id already in file, don't write again (multiple plugins)."""
        env_file = tmp_path / "env"
        env_file.write_text("export CLAUDE_SESSION_ID=abc-123\n")

        payload = {"session_id": "abc-123"}

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        content = env_file.read_text()
        # Should only appear once (not duplicated)
        assert content.count("CLAUDE_SESSION_ID=abc-123") == 1

    def test_skips_duplicate_transcript_path(self, tmp_path, hook_module):
        """If transcript_path already in file, don't write again."""
        env_file = tmp_path / "env"
        env_file.write_text("export CLAUDE_TRANSCRIPT_PATH=/path/to/transcript.jsonl\n")

        payload = {
            "session_id": "new-session",
            "transcript_path": "/path/to/transcript.jsonl"
        }

        with patch.dict("os.environ", {"CLAUDE_ENV_FILE": str(env_file)}):
            with patch("sys.stdin", StringIO(json.dumps(payload))):
                result = hook_module.main()

        assert result == 0
        content = env_file.read_text()
        # Session ID should be added, transcript path should not be duplicated
        assert "CLAUDE_SESSION_ID=new-session" in content
        assert content.count("CLAUDE_TRANSCRIPT_PATH=/path/to/transcript.jsonl") == 1
