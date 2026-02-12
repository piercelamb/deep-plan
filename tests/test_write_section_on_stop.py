"""Tests for write-section-on-stop.py - frontmatter hook for section-writer."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# Import wait_for_stable_file directly for unit testing
# The script uses hyphens in its filename, so we need importlib
import importlib.util

_hook_path = Path(__file__).parent.parent / "scripts" / "hooks" / "write-section-on-stop.py"
_spec = importlib.util.spec_from_file_location("write_section_on_stop", _hook_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
wait_for_stable_file = _mod.wait_for_stable_file


def get_test_env(tmp_path: Path) -> dict:
    """Get environment dict with HOME set to tmp_path but PATH preserved."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    return env


class TestWriteSectionOnStop:
    """Tests for write-section-on-stop.py Stop hook."""

    @pytest.fixture
    def hook_script(self):
        """Return path to the hook script."""
        return Path(__file__).parent.parent / "scripts" / "hooks" / "write-section-on-stop.py"

    def test_extracts_prompt_file_from_user_message(self, hook_script, tmp_path):
        """Should extract prompt file path from 'Read /path and execute...'"""
        # Create sections directory
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir()

        # Create .prompts directory with prompt file
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-01-foundation-prompt.md"
        prompt_file.write_text("# Section 01 Prompt\n\nGenerate content...")

        # Create transcript with user message containing prompt path
        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": f"Read {prompt_file} and execute the instructions."
                }
            }),
            json.dumps({
                "message": {
                    "role": "assistant",
                    "content": "# Section 01: Foundation\n\nThis is the section content."
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        # Run hook
        payload = {
            "agent_transcript_path": str(transcript_path)
        }

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0

        # Verify file was written to correct location
        output_file = sections_dir / "section-01-foundation.md"
        assert output_file.exists()
        assert "# Section 01: Foundation" in output_file.read_text()

    def test_derives_destination_from_prompt_path(self, hook_script, tmp_path):
        """Should derive sections_dir and filename from prompt path."""
        # Create nested sections directory
        sections_dir = tmp_path / "planning" / "feature-x" / "sections"
        sections_dir.mkdir(parents=True)

        # Create .prompts directory
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-05-api-prompt.md"
        prompt_file.write_text("# Prompt")

        # Create transcript
        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": f"Read {prompt_file} and execute the instructions."
                }
            }),
            json.dumps({
                "message": {
                    "role": "assistant",
                    "content": "# Section 05: API"
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0

        # Should derive filename correctly (remove -prompt suffix)
        output_file = sections_dir / "section-05-api.md"
        assert output_file.exists()

    def test_extracts_content_from_string_format(self, hook_script, tmp_path):
        """Should handle content as plain string."""
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir()
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-01-test-prompt.md"
        prompt_file.write_text("# Prompt")

        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": f"Read {prompt_file} and execute"
                }
            }),
            json.dumps({
                "message": {
                    "role": "assistant",
                    "content": "# String Content\n\nThis is string format."  # String, not list
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0
        output_file = sections_dir / "section-01-test.md"
        assert output_file.exists()
        assert "String Content" in output_file.read_text()

    def test_extracts_content_from_blocks_format(self, hook_script, tmp_path):
        """Should handle content as list of blocks."""
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir()
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-02-blocks-prompt.md"
        prompt_file.write_text("# Prompt")

        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": f"Read {prompt_file} and execute"
                }
            }),
            json.dumps({
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "# Blocks Content"},
                        {"type": "tool_use", "id": "123", "name": "Read", "input": {}},
                        {"type": "text", "text": "More content here."}
                    ]
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0
        output_file = sections_dir / "section-02-blocks.md"
        assert output_file.exists()
        content = output_file.read_text()
        assert "Blocks Content" in content
        assert "More content here" in content

    def test_writes_file_to_correct_location(self, hook_script, tmp_path):
        """Should write content to sections_dir/filename."""
        sections_dir = tmp_path / "my-project" / "planning" / "sections"
        sections_dir.mkdir(parents=True)
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-07-final-prompt.md"
        prompt_file.write_text("# Prompt")

        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": f"Read {prompt_file} and execute"
                }
            }),
            json.dumps({
                "message": {
                    "role": "assistant",
                    "content": "# Final Section\n\nContent here."
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0

        # Verify written to exactly the right location
        expected_path = sections_dir / "section-07-final.md"
        assert expected_path.exists()
        assert expected_path.read_text() == "# Final Section\n\nContent here."

    def test_handles_missing_transcript(self, hook_script, tmp_path):
        """Should exit gracefully if transcript missing."""
        payload = {
            "agent_transcript_path": "/nonexistent/transcript.jsonl"
        }

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        # Should return 0 (hooks should not fail)
        assert result.returncode == 0

    def test_handles_missing_prompt_file(self, hook_script, tmp_path):
        """Should exit gracefully if prompt file missing."""
        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": "Read /nonexistent/prompt.md and execute"
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        # Should return 0 (hooks should not fail)
        assert result.returncode == 0

    def test_handles_invalid_json_payload(self, hook_script, tmp_path):
        """Should exit gracefully on invalid JSON input."""
        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input="not valid json",
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0

    def test_handles_missing_agent_transcript_path(self, hook_script, tmp_path):
        """Should exit gracefully if agent_transcript_path missing from payload."""
        payload = {"session_id": "abc123"}  # No agent_transcript_path

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0

    def test_handles_sections_dir_not_existing(self, hook_script, tmp_path):
        """Should exit gracefully if sections_dir doesn't exist."""
        # Create prompts dir but NOT sections dir (parent won't exist)
        prompts_dir = tmp_path / "sections" / ".prompts"
        prompts_dir.mkdir(parents=True)
        prompt_file = prompts_dir / "section-01-test-prompt.md"
        prompt_file.write_text("# Prompt")

        # Now delete the sections dir (keep .prompts orphaned - unusual but possible)
        import shutil
        shutil.rmtree(tmp_path / "sections")
        prompts_dir.mkdir(parents=True)  # Recreate just .prompts
        prompt_file.write_text("# Prompt")

        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {
                    "role": "user",
                    "content": f"Read {prompt_file} and execute"
                }
            }),
            json.dumps({
                "message": {
                    "role": "assistant",
                    "content": "# Test Content"
                }
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        # Should return 0 (hooks should not fail)
        assert result.returncode == 0

    def test_uses_last_assistant_message(self, hook_script, tmp_path):
        """Should use the LAST assistant text message as content."""
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir()
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-01-multi-prompt.md"
        prompt_file.write_text("# Prompt")

        transcript_path = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps({
                "message": {"role": "user", "content": f"Read {prompt_file} and execute"}
            }),
            json.dumps({
                "message": {"role": "assistant", "content": "First response - not this one"}
            }),
            json.dumps({
                "message": {"role": "user", "content": "Continue please"}
            }),
            json.dumps({
                "message": {"role": "assistant", "content": "# Final Content\n\nThis is the last response."}
            }),
        ]
        transcript_path.write_text("\n".join(lines))

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path)
        )

        assert result.returncode == 0
        output_file = sections_dir / "section-01-multi.md"
        assert output_file.exists()
        content = output_file.read_text()
        assert "Final Content" in content
        assert "First response" not in content


class TestWaitForStableFile:
    """Tests for wait_for_stable_file() — the race condition fix."""

    @pytest.fixture
    def hook_script(self):
        """Return path to the hook script."""
        return Path(__file__).parent.parent / "scripts" / "hooks" / "write-section-on-stop.py"

    def test_static_file_returns_quickly(self, tmp_path):
        """A file that already exists and isn't changing should return fast."""
        f = tmp_path / "stable.jsonl"
        f.write_text("line1\nline2\n")

        start = time.time()
        wait_for_stable_file(str(f), stability_ms=100, poll_ms=25)
        elapsed = time.time() - start

        # Should take ~100-150ms (stability window + 1-2 polls), not 5s timeout
        assert elapsed < 0.5

    def test_growing_file_waits_until_stable(self, tmp_path):
        """Should wait for file to stop growing before returning."""
        f = tmp_path / "growing.jsonl"
        f.write_text("initial\n")

        writes_done = threading.Event()

        def append_lines():
            """Append lines with small delays to simulate ongoing writes."""
            for i in range(5):
                time.sleep(0.03)  # 30ms between writes
                with open(f, "a") as fh:
                    fh.write(f"line {i}\n")
            writes_done.set()

        writer = threading.Thread(target=append_lines)
        writer.start()

        wait_for_stable_file(str(f), stability_ms=150, poll_ms=25)

        # All writes should be done before we return
        assert writes_done.is_set()
        content = f.read_text()
        assert "line 4" in content  # Last line was written

        writer.join()

    def test_timeout_falls_through(self, tmp_path):
        """Should return after timeout even if file keeps changing."""
        f = tmp_path / "forever.jsonl"
        f.write_text("start\n")

        stop_writing = threading.Event()

        def keep_writing():
            i = 0
            while not stop_writing.is_set():
                time.sleep(0.02)
                with open(f, "a") as fh:
                    fh.write(f"line {i}\n")
                i += 1

        writer = threading.Thread(target=keep_writing)
        writer.start()

        start = time.time()
        wait_for_stable_file(str(f), stability_ms=100, timeout_s=0.5, poll_ms=25)
        elapsed = time.time() - start

        stop_writing.set()
        writer.join()

        # Should have timed out around 0.5s, not waited for stability
        assert elapsed >= 0.4
        assert elapsed < 1.0

    def test_nonexistent_file_times_out(self, tmp_path):
        """Should timeout gracefully if file doesn't exist."""
        start = time.time()
        wait_for_stable_file(str(tmp_path / "nope.jsonl"), stability_ms=50, timeout_s=0.3, poll_ms=25)
        elapsed = time.time() - start

        assert elapsed >= 0.25
        assert elapsed < 0.6

    def test_race_condition_simulation(self, hook_script, tmp_path):
        """Simulate the actual race: transcript incomplete when hook starts, completed during wait.

        This reproduces the exact bug from FINDINGS.md where the hook reads the
        transcript before the final assistant message is written.
        """
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir()
        prompts_dir = sections_dir / ".prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "section-01-race-prompt.md"
        prompt_file.write_text("# Prompt")

        # Build a transcript that simulates the race:
        # - Lines 1-3: user msg, assistant tool_use, user tool_result
        # - Line 4: small intermediate assistant text (the WRONG content)
        # - Line 5: the REAL section content (large assistant text)
        # - Line 6: final progress event
        incomplete_lines = [
            json.dumps({"message": {"role": "user", "content": f"Read {prompt_file} and execute"}}),
            json.dumps({"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}}),
            json.dumps({"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "file contents"}]}}),
            json.dumps({"message": {"role": "assistant", "content": "Let me try a different approach..."}}),
        ]
        final_lines = [
            json.dumps({"message": {"role": "assistant", "content": "# Race Test Section\n\nThis is the REAL section content with lots of detail."}}),
            json.dumps({"progress": {"type": "final"}}),
        ]

        transcript_path = tmp_path / "transcript.jsonl"
        # Write incomplete transcript (missing last 2 lines — the exact race scenario)
        transcript_path.write_text("\n".join(incomplete_lines))

        def append_final_lines():
            """Simulate Claude Code flushing the final entries after ~100ms."""
            time.sleep(0.1)
            with open(transcript_path, "a") as fh:
                fh.write("\n" + "\n".join(final_lines))

        writer = threading.Thread(target=append_final_lines)
        writer.start()

        payload = {"agent_transcript_path": str(transcript_path)}

        result = subprocess.run(
            ["uv", "run", str(hook_script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=get_test_env(tmp_path),
        )

        writer.join()

        assert result.returncode == 0

        output_file = sections_dir / "section-01-race.md"
        assert output_file.exists()
        content = output_file.read_text()
        # Must contain the REAL section content, not the intermediate message
        assert "REAL section content" in content
        assert "different approach" not in content
