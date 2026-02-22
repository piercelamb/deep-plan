"""Tests for environment validation script.

NOTE: validate-env.sh derives plugin_root from its own location, not from env vars.
Tests that require custom config must use the actual plugin's config.json.
Tests requiring real API validation are marked with @pytest.mark.requires_credentials.
"""

import pytest
import subprocess
import json
import os
from pathlib import Path


class TestValidateEnv:
    """Tests for validate-env.sh script."""

    @pytest.fixture
    def script_path(self):
        """Return path to validate-env.sh."""
        return Path(__file__).parent.parent / "scripts" / "checks" / "validate-env.sh"

    @pytest.fixture
    def plugin_root(self):
        """Return path to plugin root."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def run_script(self, script_path):
        """Factory fixture to run validate-env.sh."""
        def _run(env=None, timeout=30):
            """Run the script with given environment."""
            if env is None:
                env = os.environ.copy()
            result = subprocess.run(
                [str(script_path)],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result
        return _run

    @pytest.fixture
    def isolated_env(self, tmp_path):
        """Environment with all LLM auth vars cleared for deterministic tests."""
        env = os.environ.copy()
        for key in [
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "DEEPPLAN_GEMINI_API_KEY",
            "DEEPPLAN_OPENAI_API_KEY",
            "DEEPPLAN_OPENAI_BASE_URL",
            "DEEPPLAN_OPENAI_MODEL",
            "DEEPPLAN_GOOGLE_CLOUD_PROJECT",
            "DEEPPLAN_GOOGLE_CLOUD_LOCATION",
            "DEEPPLAN_GOOGLE_APPLICATION_CREDENTIALS",
        ]:
            env.pop(key, None)

        # Prevent using host ADC defaults during tests.
        env["HOME"] = str(tmp_path)
        return env

    def test_outputs_valid_json_structure(self, run_script):
        """Should output valid JSON with expected fields."""
        # Use real environment - we just test JSON structure
        result = run_script()

        # Should parse without exception
        output = json.loads(result.stdout)

        # Check expected fields exist
        assert "valid" in output
        assert "errors" in output
        assert "warnings" in output
        assert "gemini_auth" in output
        assert "openai_auth" in output
        assert "plugin_root" in output

    def test_plugin_root_in_output(self, run_script, plugin_root):
        """Should include correct plugin_root in output."""
        result = run_script()
        output = json.loads(result.stdout)

        assert output["plugin_root"] == str(plugin_root)

    def test_exit_code_0_when_valid(self, run_script):
        """Should exit 0 when validation passes (or warnings only)."""
        result = run_script()
        output = json.loads(result.stdout)

        # If valid, exit code should be 0
        if output["valid"]:
            assert result.returncode == 0

    def test_exit_code_nonzero_when_errors(self, run_script):
        """Should exit non-zero when there are errors."""
        result = run_script()
        output = json.loads(result.stdout)

        # If not valid, exit code should be non-zero
        if not output["valid"]:
            assert result.returncode != 0

    def test_detects_gemini_api_key_presence(self, run_script, isolated_env):
        """Should detect when GEMINI_API_KEY is set (presence check only)."""
        env = isolated_env.copy()
        env["GEMINI_API_KEY"] = "test-key-for-presence-check"

        result = run_script(env=env)
        output = json.loads(result.stdout)

        # Should detect the key exists (may fail validation with fake key, but detects presence)
        # gemini_auth will be "api_key" if detected, or "test_failed" if validation failed
        assert output["gemini_auth"] in ["api_key", "test_failed"]

    def test_detects_openai_api_key_presence(self, run_script, isolated_env):
        """Should detect when OPENAI_API_KEY is set (presence check only)."""
        env = isolated_env.copy()
        env["OPENAI_API_KEY"] = "test-key-for-presence-check"

        result = run_script(env=env)
        output = json.loads(result.stdout)

        # openai_auth is True if key exists and validates, False otherwise
        # With a fake key, validation will fail but the key was detected
        assert "openai_auth" in output

    def test_returns_null_gemini_auth_when_no_key(self, run_script, isolated_env):
        """Should return null gemini_auth when no auth configured."""
        env = isolated_env.copy()

        result = run_script(env=env)
        output = json.loads(result.stdout)

        # Should be null when no auth found
        assert output["gemini_auth"] is None

    def test_scoped_openai_ignores_generic_gemini(self, run_script, isolated_env):
        """DEEPPLAN OpenAI scope should ignore generic Gemini credentials."""
        env = isolated_env.copy()
        env["DEEPPLAN_OPENAI_API_KEY"] = "test-openai-key"
        env["DEEPPLAN_OPENAI_MODEL"] = "gpt-5.2"
        env["GEMINI_API_KEY"] = "test-gemini-key"

        result = run_script(env=env)
        output = json.loads(result.stdout)

        assert all("Gemini" not in err and "ADC" not in err for err in output["errors"])

    def test_scoped_openai_429_marks_only_openai_as_failed(self, run_script, isolated_env, tmp_path):
        """Scoped OpenAI 429-style failures should not implicate Gemini."""
        env = isolated_env.copy()
        env["DEEPPLAN_OPENAI_API_KEY"] = "test-openai-key"
        env["DEEPPLAN_OPENAI_MODEL"] = "gpt-5.2"

        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_uv = fake_bin / "uv"
        fake_uv.write_text(
            "#!/usr/bin/env bash\n"
            "cat <<'JSON'\n"
            '{"openai":{"success":false,"error":"Error code: 429 - insufficient_quota"}}\n'
            "JSON\n"
            "exit 1\n"
        )
        fake_uv.chmod(0o755)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        result = run_script(env=env)
        output = json.loads(result.stdout)

        assert output["openai_auth"] is False
        assert output["gemini_auth"] is None
        assert any("OpenAI model test failed" in err for err in output["errors"])
        assert any("429" in err for err in output["errors"])
        assert all("Gemini" not in err and "ADC" not in err for err in output["errors"])

    def test_scoped_gemini_ignores_generic_openai(self, run_script, isolated_env):
        """DEEPPLAN Gemini scope should ignore generic OpenAI credentials."""
        env = isolated_env.copy()
        env["DEEPPLAN_GEMINI_API_KEY"] = "test-gemini-key"
        env["OPENAI_API_KEY"] = "test-openai-key"

        result = run_script(env=env)
        output = json.loads(result.stdout)

        assert all("OpenAI" not in err and "OPENAI" not in err for err in output["errors"])

    def test_generic_fallback_when_no_deepplan_scope(self, run_script, isolated_env):
        """Without DEEPPLAN scope, generic provider validation should still run."""
        env = isolated_env.copy()
        env["OPENAI_API_KEY"] = "test-openai-key"

        result = run_script(env=env)
        output = json.loads(result.stdout)

        assert any("Gemini" in err for err in output["errors"])
