"""Integration tests for deep-plan plugin."""

import pytest
import subprocess
import json
import os
from pathlib import Path


class TestFullWorkflow:
    """End-to-end workflow tests."""

    @pytest.fixture
    def plugin_root(self):
        """Return path to plugin root."""
        return Path(__file__).parent.parent

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

        env["HOME"] = str(tmp_path)
        return env

    @pytest.mark.integration
    def test_validate_env_outputs_valid_json(self, plugin_root):
        """Should run validate-env.sh and return valid JSON structure."""
        env = os.environ.copy()

        result = subprocess.run(
            [str(plugin_root / "scripts" / "checks" / "validate-env.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should output valid JSON regardless of validation result
        output = json.loads(result.stdout)
        assert "valid" in output
        assert "errors" in output
        assert "warnings" in output
        assert "gemini_auth" in output
        assert "openai_auth" in output
        assert "plugin_root" in output

    @pytest.mark.integration
    def test_review_exits_1_without_auth(self, plugin_root, tmp_path, isolated_env):
        """Should exit 1 when no LLM auth configured."""
        import sys
        sys.path.insert(0, str(plugin_root / "scripts"))
        from lib.config import create_session_config

        # Create a planning dir with required files
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        (planning_dir / "claude-plan.md").write_text("# Test Plan\n\nThis is a test.")

        # Create session config (required by review.py)
        create_session_config(
            planning_dir=planning_dir,
            plugin_root=str(plugin_root),
            initial_file=str(planning_dir / "spec.md"),
        )

        env = isolated_env.copy()

        result = subprocess.run(
            ["uv", "run",
             str(plugin_root / "scripts" / "llm_clients" / "review.py"),
             "--planning-dir", str(planning_dir)],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert "error" in output

    @pytest.mark.integration
    def test_validate_env_scoped_openai_ignores_generic_gemini(self, plugin_root, isolated_env):
        """DEEPPLAN OpenAI scope should not fail on generic Gemini state."""
        env = isolated_env.copy()
        env["DEEPPLAN_OPENAI_API_KEY"] = "test-openai-key"
        env["DEEPPLAN_OPENAI_MODEL"] = "gpt-5.2"
        env["GEMINI_API_KEY"] = "test-gemini-key"

        result = subprocess.run(
            [str(plugin_root / "scripts" / "checks" / "validate-env.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = json.loads(result.stdout)
        assert all("Gemini" not in err and "ADC" not in err for err in output["errors"])

    @pytest.mark.integration
    def test_validate_env_scoped_openai_429_class_failure_signature(self, plugin_root, isolated_env, tmp_path):
        """Scoped OpenAI failures should produce OpenAI-only model test errors."""
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

        result = subprocess.run(
            [str(plugin_root / "scripts" / "checks" / "validate-env.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = json.loads(result.stdout)
        assert output["openai_auth"] is False
        assert output["gemini_auth"] is None
        assert any("OpenAI model test failed" in err for err in output["errors"])
        assert any("429" in err for err in output["errors"])
        assert all("Gemini" not in err and "ADC" not in err for err in output["errors"])

    @pytest.mark.integration
    def test_validate_env_scoped_gemini_ignores_generic_openai(self, plugin_root, isolated_env):
        """DEEPPLAN Gemini scope should not fail on generic OpenAI state."""
        env = isolated_env.copy()
        env["DEEPPLAN_GEMINI_API_KEY"] = "test-gemini-key"
        env["OPENAI_API_KEY"] = "test-openai-key"

        result = subprocess.run(
            [str(plugin_root / "scripts" / "checks" / "validate-env.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = json.loads(result.stdout)
        assert all("OpenAI" not in err and "OPENAI" not in err for err in output["errors"])

    @pytest.mark.integration
    def test_validate_env_generic_fallback_without_deepplan_scope(self, plugin_root, isolated_env):
        """Without DEEPPLAN scope, generic provider fallback should still apply."""
        env = isolated_env.copy()
        env["OPENAI_API_KEY"] = "test-openai-key"

        result = subprocess.run(
            [str(plugin_root / "scripts" / "checks" / "validate-env.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = json.loads(result.stdout)
        assert any("Gemini" in err for err in output["errors"])


class TestPluginStructure:
    """Tests that validate plugin structure is correct."""

    @pytest.fixture
    def plugin_root(self):
        """Return path to plugin root."""
        return Path(__file__).parent.parent

    def test_plugin_json_exists(self, plugin_root):
        """Should have plugin.json in .claude-plugin/ directory."""
        plugin_json = plugin_root / ".claude-plugin" / "plugin.json"
        assert plugin_json.exists(), f"Missing: {plugin_json}"

    def test_plugin_json_valid(self, plugin_root):
        """Should have valid JSON in plugin.json."""
        plugin_json = plugin_root / ".claude-plugin" / "plugin.json"
        data = json.loads(plugin_json.read_text())
        assert "name" in data, "plugin.json missing 'name'"
        assert "description" in data, "plugin.json missing 'description'"
        assert "version" in data, "plugin.json missing 'version'"

    def test_config_json_exists(self, plugin_root):
        """Should have config.json at plugin root."""
        config_json = plugin_root / "config.json"
        assert config_json.exists(), f"Missing: {config_json}"

    def test_config_json_valid(self, plugin_root):
        """Should have valid JSON in config.json with expected sections."""
        config_json = plugin_root / "config.json"
        data = json.loads(config_json.read_text())
        assert "context" in data, "config.json missing 'context'"
        assert "external_review" in data, "config.json missing 'external_review'"
        assert "models" in data, "config.json missing 'models'"
        assert "llm_client" in data, "config.json missing 'llm_client'"

    def test_skill_exists(self, plugin_root):
        """Should have deep-plan skill at skills/deep-plan/SKILL.md."""
        skill_file = plugin_root / "skills" / "deep-plan" / "SKILL.md"
        assert skill_file.exists(), f"Missing: {skill_file}"

    def test_skill_preflight_path_supports_hybrid_lookup(self, plugin_root):
        """SKILL preflight path discovery should prioritize plugin root and installed cache before pwd fallback."""
        skill_file = plugin_root / "skills" / "deep-plan" / "SKILL.md"
        content = skill_file.read_text()

        # Check for the resolve_script_path function
        assert 'resolve_script_path()' in content
        assert 'local script_rel_path="$1"' in content

        # Strategy 1: CLAUDE_PLUGIN_ROOT priority
        assert 'CLAUDE_PLUGIN_ROOT' in content
        assert 'local candidate="$CLAUDE_PLUGIN_ROOT/$script_rel_path"' in content

        # Strategy 2: installed plugin cache fallback
        assert 'for root in "$HOME/.claude/plugins/cache" "$HOME/.claude/plugins"; do' in content
        assert 'find "$root" -path "*/deep-plan/*/$script_rel_path"' in content

        # Strategy 3: pwd fallback (dev only)
        assert 'find "$(pwd)" -path "*/$script_rel_path" -type f' in content

        # Check for usage
        assert 'resolve_script_path "scripts/checks/validate-env.sh"' in content

        # Check for helpful diagnostics
        assert 'Attempted roots:' in content
        assert 'Reinstall plugin: /plugin install deep-plan' in content

    def test_skill_recoverable_preflight_offers_three_way_choice(self, plugin_root):
        """Recoverable preflight failures should expose opus/skip/exit options."""
        skill_file = plugin_root / "skills" / "deep-plan" / "SKILL.md"
        content = skill_file.read_text()

        assert 'External LLM preflight failed. How should plan review be handled?' in content
        assert 'Use Claude Opus for review (Recommended)' in content
        assert 'Skip external review' in content
        assert 'Exit to configure LLMs' in content
        assert '429' in content

    def test_prompts_exist(self, plugin_root):
        """Should have plan_reviewer prompts."""
        system_prompt = plugin_root / "prompts" / "plan_reviewer" / "system"
        user_prompt = plugin_root / "prompts" / "plan_reviewer" / "user"
        assert system_prompt.exists(), f"Missing: {system_prompt}"
        assert user_prompt.exists(), f"Missing: {user_prompt}"

    def test_lib_modules_exist(self, plugin_root):
        """Should have lib modules."""
        config_py = plugin_root / "scripts" / "lib" / "config.py"
        prompts_py = plugin_root / "scripts" / "lib" / "prompts.py"
        assert config_py.exists(), f"Missing: {config_py}"
        assert prompts_py.exists(), f"Missing: {prompts_py}"

    def test_check_scripts_exist(self, plugin_root):
        """Should have check scripts."""
        validate_env = plugin_root / "scripts" / "checks" / "validate-env.sh"
        check_context = plugin_root / "scripts" / "checks" / "check-context-decision.py"
        assert validate_env.exists(), f"Missing: {validate_env}"
        assert check_context.exists(), f"Missing: {check_context}"

    def test_llm_clients_exist(self, plugin_root):
        """Should have LLM client scripts."""
        # Note: Directory is llm_clients (underscore) for Python import compatibility
        review = plugin_root / "scripts" / "llm_clients" / "review.py"
        assert review.exists(), f"Missing: {review}"


class TestOutputFormat:
    """Tests that validate output format matches implementation system requirements."""

    def test_section_index_has_required_format(self):
        """Should have section index format with dependency graph."""
        # This is a documentation test - verify the expected format
        expected_headers = [
            "# Implementation Sections Index",
            "## Dependency Graph",
            "## Execution Order",
        ]

        # The format is specified - this test documents the contract
        sample_index = """# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01 | - | section-02 | Yes |

## Execution Order

1. section-01 (no dependencies)
"""
        for header in expected_headers:
            assert header in sample_index, f"Missing header: {header}"

    def test_planning_state_json_schema(self):
        """Should match .planning-state.json schema."""
        # Document the expected schema
        sample_state = {
            "current_step": 10,
            "completed_steps": [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "planning_dir": "/path/to/planning",
            "has_research": True,
            "has_spec": True,
            "has_plan": True,
            "external_review": {
                "current_iteration": 1,
                "total_iterations": 2,
                "gemini_available": True,
                "chatgpt_available": True
            },
            "last_updated": "2026-01-05T10:30:00Z"
        }

        # Verify required fields
        assert "current_step" in sample_state
        assert "completed_steps" in sample_state
        assert "planning_dir" in sample_state
        assert "external_review" in sample_state
        assert isinstance(sample_state["completed_steps"], list)
