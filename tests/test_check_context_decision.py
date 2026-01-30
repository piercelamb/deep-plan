"""Tests for check-context-decision.py script."""

import pytest
import subprocess
import json
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lib.config import create_session_config


class TestCheckContextDecision:
    """Tests for check-context-decision.py script."""

    @pytest.fixture
    def script_path(self):
        """Return path to check-context-decision.py."""
        return Path(__file__).parent.parent / "scripts" / "checks" / "check-context-decision.py"

    @pytest.fixture
    def plugin_root(self):
        """Return path to plugin root."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def planning_dir_with_config(self, tmp_path, plugin_root):
        """Create a planning directory with session config."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()

        # Create session config (copies global config + adds session keys)
        create_session_config(
            planning_dir=planning_dir,
            plugin_root=str(plugin_root),
            initial_file=str(planning_dir / "spec.md"),
        )

        return planning_dir

    @pytest.fixture
    def run_script(self, script_path, plugin_root):
        """Factory fixture to run check-context-decision.py."""
        def _run(planning_dir: Path, upcoming_operation: str, config_override: dict = None, timeout=10):
            """Run the script with given operation name and planning dir."""
            env = os.environ.copy()

            cmd = [
                "uv", "run", str(script_path),
                "--planning-dir", str(planning_dir),
                "--upcoming-operation", upcoming_operation
            ]

            # If config override provided, update the session config
            if config_override:
                config_path = planning_dir / "deep_plan_config.json"
                current_config = json.loads(config_path.read_text())
                # Deep merge the override
                for key, value in config_override.items():
                    if isinstance(value, dict) and key in current_config:
                        current_config[key] = {**current_config.get(key, {}), **value}
                    else:
                        current_config[key] = value
                config_path.write_text(json.dumps(current_config, indent=2))

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return result
        return _run

    def test_default_config_prompts(self, run_script, planning_dir_with_config):
        """Should prompt when check_enabled is true (default)."""
        result = run_script(planning_dir_with_config, "External LLM Review")

        assert result.returncode == 0
        output = json.loads(result.stdout)

        assert output["action"] == "prompt"
        assert output["check_enabled"] is True
        assert "prompt" in output
        assert "message" in output["prompt"]
        assert "options" in output["prompt"]

    def test_prompt_includes_operation_name(self, run_script, planning_dir_with_config):
        """Should include upcoming operation in prompt message."""
        result = run_script(planning_dir_with_config, "Split Plan Into Sections")

        assert result.returncode == 0
        output = json.loads(result.stdout)

        assert "Split Plan Into Sections" in output["prompt"]["message"]

    def test_prompt_options_format(self, run_script, planning_dir_with_config):
        """Should return properly formatted prompt options."""
        result = run_script(planning_dir_with_config, "Test Operation")

        assert result.returncode == 0
        output = json.loads(result.stdout)

        options = output["prompt"]["options"]
        assert len(options) == 2

        # Check each option has label and description
        for opt in options:
            assert "label" in opt
            assert "description" in opt

        # Check specific options
        labels = [opt["label"] for opt in options]
        assert "Continue" in labels
        assert "/clear + re-run" in labels

    def test_check_disabled_skips(self, run_script, planning_dir_with_config):
        """Should skip when check_enabled is false in config."""
        result = run_script(
            planning_dir_with_config,
            "Test Operation",
            config_override={"context": {"check_enabled": False}}
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)

        assert output["action"] == "skip"
        assert output["check_enabled"] is False
        assert "prompt" not in output

    def test_missing_config_defaults_to_prompt(self, script_path, tmp_path):
        """Should default to prompting if config can't be loaded."""
        # Create planning dir without session config
        planning_dir = tmp_path / "no_config"
        planning_dir.mkdir()

        result = subprocess.run(
            [
                "uv", "run", str(script_path),
                "--planning-dir", str(planning_dir),
                "--upcoming-operation", "Test"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)

        # Should default to prompting when config is missing
        assert output["action"] == "prompt"
        assert output["check_enabled"] is True
