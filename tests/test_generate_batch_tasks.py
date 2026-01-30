"""Tests for generate-batch-tasks.py script."""

import pytest
import subprocess
import json
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lib.config import create_session_config


class TestGenerateBatchTasks:
    """Tests for generate-batch-tasks.py script."""

    @pytest.fixture
    def script_path(self):
        """Return path to generate-batch-tasks.py."""
        return Path(__file__).parent.parent / "scripts" / "checks" / "generate-batch-tasks.py"

    @pytest.fixture
    def plugin_root(self):
        """Return path to plugin root."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def run_script(self, script_path, plugin_root):
        """Factory fixture to run generate-batch-tasks.py."""
        def _run(planning_dir: Path, batch_num: int, timeout=10):
            """Run the script with given planning directory and batch number.

            Creates session config if it doesn't exist.
            """
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)

            # Create session config if needed
            config_path = planning_dir / "deep_plan_config.json"
            if not config_path.exists():
                create_session_config(
                    planning_dir=planning_dir,
                    plugin_root=str(plugin_root),
                    initial_file=str(planning_dir / "spec.md"),
                )

            result = subprocess.run(
                [
                    "uv", "run", str(script_path),
                    "--planning-dir", str(planning_dir),
                    "--batch-num", str(batch_num),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result
        return _run

    @pytest.fixture
    def sample_index_content(self):
        """Sample index.md content with SECTION_MANIFEST block."""
        return """<!-- SECTION_MANIFEST
section-01-setup
section-02-api
section-03-database
END_MANIFEST -->

# Implementation Sections Index
"""

    @pytest.fixture
    def large_index_content(self):
        """Index with 10 sections (two batches)."""
        sections = [f"section-{i:02d}-s{i}" for i in range(1, 11)]
        manifest = "\n".join(sections)
        return f"""<!-- SECTION_MANIFEST
{manifest}
END_MANIFEST -->

# Implementation Sections Index
"""

    def test_no_index_returns_error(self, run_script, tmp_path):
        """Should return error when no index.md exists."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "index.md" in output["error"]

    def test_invalid_batch_num_returns_error(self, run_script, tmp_path, sample_index_content):
        """Should return error for invalid batch number."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        # Batch 0 is invalid
        result = run_script(planning_dir, batch_num=0)
        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "Invalid batch number" in output["error"]

        # Batch 2 doesn't exist (only 3 sections = 1 batch)
        result = run_script(planning_dir, batch_num=2)
        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "Invalid batch number" in output["error"]

    def test_successful_batch_outputs_json(self, run_script, tmp_path, sample_index_content):
        """Should output valid JSON for valid batch."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["batch_num"] == 1
        assert output["total_batches"] == 1
        assert len(output["sections"]) == 3
        assert len(output["prompt_files"]) == 3

    def test_json_contains_all_batch_sections(self, run_script, tmp_path, sample_index_content):
        """JSON should list all sections in batch."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        # Should have 3 sections in batch 1
        assert "section-01-setup.md" in output["sections"]
        assert "section-02-api.md" in output["sections"]
        assert "section-03-database.md" in output["sections"]

    def test_prompt_files_contain_planning_dir_path(self, run_script, tmp_path, sample_index_content):
        """Prompt file paths should contain the planning directory path."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        # All prompt files should contain planning dir path
        for prompt_file in output["prompt_files"]:
            assert str(planning_dir.resolve()) in prompt_file

    def test_multi_batch_first_batch(self, run_script, tmp_path, large_index_content):
        """First batch should have 7 sections for 10-section plan."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(large_index_content)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["batch_num"] == 1
        assert output["total_batches"] == 2
        assert len(output["sections"]) == 7
        # Batch 1 should have sections 1-7
        for i in range(1, 8):
            assert f"section-{i:02d}-s{i}.md" in output["sections"]
        # Should NOT have sections 8-10
        assert "section-08-s8.md" not in output["sections"]

    def test_multi_batch_second_batch(self, run_script, tmp_path, large_index_content):
        """Second batch should have remaining 3 sections for 10-section plan."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(large_index_content)

        result = run_script(planning_dir, batch_num=2)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["batch_num"] == 2
        assert output["total_batches"] == 2
        assert len(output["sections"]) == 3
        # Batch 2 should have sections 8-10
        assert "section-08-s8.md" in output["sections"]
        assert "section-09-s9.md" in output["sections"]
        assert "section-10-s10.md" in output["sections"]
        # Should NOT have sections 1-7
        assert "section-01-s1.md" not in output["sections"]

    def test_json_has_correct_structure(self, run_script, tmp_path, sample_index_content):
        """JSON output should have all required fields."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        # Check for required fields
        assert "success" in output
        assert "error" in output
        assert "batch_num" in output
        assert "total_batches" in output
        assert "sections" in output
        assert "prompt_files" in output

    def test_requires_session_config(self, script_path, tmp_path):
        """Should fail if session config doesn't exist."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()

        # Don't create session config - it should fail
        result = subprocess.run(
            [
                "uv", "run", str(script_path),
                "--planning-dir", str(planning_dir),
                "--batch-num", "1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "config" in output["error"].lower()

    def test_prompt_files_are_created(self, run_script, tmp_path, sample_index_content):
        """Prompt files should be created in .prompts directory."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)

        # Verify prompt files exist
        for prompt_file in output["prompt_files"]:
            assert Path(prompt_file).exists()

        # Verify they're in the .prompts directory
        prompts_dir = sections_dir / ".prompts"
        assert prompts_dir.exists()
        assert len(list(prompts_dir.glob("*.md"))) == 3

    def test_all_sections_complete_returns_nothing_to_do(self, run_script, tmp_path, sample_index_content):
        """Should return 'nothing to do' message when all sections exist."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        # Create all the section files (they exist, so nothing to generate)
        (sections_dir / "section-01-setup.md").write_text("# Setup\nContent")
        (sections_dir / "section-02-api.md").write_text("# API\nContent")
        (sections_dir / "section-03-database.md").write_text("# Database\nContent")

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert "message" in output
        assert "Nothing to do" in output["message"]
        assert len(output["prompt_files"]) == 0

    def test_partial_complete_only_generates_missing(self, run_script, tmp_path, sample_index_content):
        """Should only generate prompt files for missing sections."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(sample_index_content)

        # Create only the first section file
        (sections_dir / "section-01-setup.md").write_text("# Setup\nContent")

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        # Should NOT have the completed section
        assert "section-01-setup.md" not in output["sections"]
        # Should have the missing sections
        assert "section-02-api.md" in output["sections"]
        assert "section-03-database.md" in output["sections"]
        assert len(output["prompt_files"]) == 2


class TestSectionCompletionScenarios:
    """Comprehensive tests for various section completion states."""

    @pytest.fixture
    def script_path(self):
        """Return path to generate-batch-tasks.py."""
        return Path(__file__).parent.parent / "scripts" / "checks" / "generate-batch-tasks.py"

    @pytest.fixture
    def plugin_root(self):
        """Return path to plugin root."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def run_script(self, script_path, plugin_root):
        """Factory fixture to run generate-batch-tasks.py."""
        def _run(planning_dir: Path, batch_num: int, timeout=10):
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)

            config_path = planning_dir / "deep_plan_config.json"
            if not config_path.exists():
                create_session_config(
                    planning_dir=planning_dir,
                    plugin_root=str(plugin_root),
                    initial_file=str(planning_dir / "spec.md"),
                )

            result = subprocess.run(
                [
                    "uv", "run", str(script_path),
                    "--planning-dir", str(planning_dir),
                    "--batch-num", str(batch_num),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result
        return _run

    @pytest.fixture
    def twelve_section_index(self):
        """Index with 12 sections (two batches: 7 + 5)."""
        sections = [
            "section-01-foundation",
            "section-02-config",
            "section-03-parser",
            "section-04-categorizer",
            "section-05-asset-discovery",
            "section-06-validator",
            "section-07-depreciation",
            "section-08-calculator",
            "section-09-excel-writer",
            "section-10-json-writer",
            "section-11-cli",
            "section-12-regression",
        ]
        manifest = "\n".join(sections)
        return f"""<!-- SECTION_MANIFEST
{manifest}
END_MANIFEST -->

# Implementation Sections Index
"""

    def _create_section_files(self, sections_dir: Path, section_names: list):
        """Helper to create section files."""
        for name in section_names:
            (sections_dir / f"{name}.md").write_text(f"# {name}\nContent")

    # Test 1: Fresh start - all sections missing
    def test_fresh_start_generates_all_batch_tasks(self, run_script, tmp_path, twelve_section_index):
        """With no section files, batch 1 should generate prompts for all 7 sections."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["batch_num"] == 1
        assert output["total_batches"] == 2
        assert len(output["sections"]) == 7
        assert len(output["prompt_files"]) == 7

    # Test 2: All sections complete globally
    def test_all_sections_complete_globally(self, run_script, tmp_path, twelve_section_index):
        """With all section files present, should return 'All sections already written'."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        # Create all 12 section files
        all_sections = [
            "section-01-foundation", "section-02-config", "section-03-parser",
            "section-04-categorizer", "section-05-asset-discovery", "section-06-validator",
            "section-07-depreciation", "section-08-calculator", "section-09-excel-writer",
            "section-10-json-writer", "section-11-cli", "section-12-regression",
        ]
        self._create_section_files(sections_dir, all_sections)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert "message" in output
        assert "All sections already written" in output["message"]
        assert len(output["prompt_files"]) == 0

    # Test 3: Batch 1 complete, batch 2 incomplete
    def test_batch_complete_other_batches_incomplete(self, run_script, tmp_path, twelve_section_index):
        """With batch 1 complete but batch 2 missing, batch 1 returns 'Batch 1 sections already written'."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        # Create only batch 1 sections (1-7)
        batch1_sections = [
            "section-01-foundation", "section-02-config", "section-03-parser",
            "section-04-categorizer", "section-05-asset-discovery", "section-06-validator",
            "section-07-depreciation",
        ]
        self._create_section_files(sections_dir, batch1_sections)

        # Batch 1 should be complete
        result1 = run_script(planning_dir, batch_num=1)
        assert result1.returncode == 0
        output1 = json.loads(result1.stdout)
        assert "message" in output1
        assert "Batch 1 sections already written" in output1["message"]

        # Batch 2 should have tasks
        result2 = run_script(planning_dir, batch_num=2)
        assert result2.returncode == 0
        output2 = json.loads(result2.stdout)
        assert output2["batch_num"] == 2
        assert len(output2["sections"]) == 5
        assert "section-08-calculator.md" in output2["sections"]

    # Test 4: Partial batch completion
    def test_partial_batch_only_generates_missing(self, run_script, tmp_path, twelve_section_index):
        """With some sections in batch 1 complete, only generates prompts for missing ones."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        # Create only first 3 sections of batch 1
        partial_sections = ["section-01-foundation", "section-02-config", "section-03-parser"]
        self._create_section_files(sections_dir, partial_sections)

        result = run_script(planning_dir, batch_num=1)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        # Should only have 4 sections (7 - 3 = 4)
        assert len(output["sections"]) == 4
        # Should NOT have completed sections
        assert "section-01-foundation.md" not in output["sections"]
        assert "section-02-config.md" not in output["sections"]
        assert "section-03-parser.md" not in output["sections"]
        # Should have remaining sections
        assert "section-04-categorizer.md" in output["sections"]
        assert "section-05-asset-discovery.md" in output["sections"]
        assert "section-06-validator.md" in output["sections"]
        assert "section-07-depreciation.md" in output["sections"]

    # Test 5: Multi-batch with mixed completion states
    def test_mixed_completion_across_batches(self, run_script, tmp_path, twelve_section_index):
        """Test with some sections complete in both batches."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        # Create scattered sections: some from batch 1, some from batch 2
        mixed_sections = [
            "section-01-foundation",  # batch 1
            "section-03-parser",      # batch 1
            "section-05-asset-discovery",  # batch 1
            "section-08-calculator",  # batch 2
            "section-10-json-writer", # batch 2
        ]
        self._create_section_files(sections_dir, mixed_sections)

        # Batch 1 should have 4 missing (7 - 3)
        result1 = run_script(planning_dir, batch_num=1)
        assert result1.returncode == 0
        output1 = json.loads(result1.stdout)
        assert len(output1["sections"]) == 4
        assert "section-02-config.md" in output1["sections"]
        assert "section-04-categorizer.md" in output1["sections"]
        assert "section-01-foundation.md" not in output1["sections"]  # complete

        # Batch 2 should have 3 missing (5 - 2)
        result2 = run_script(planning_dir, batch_num=2)
        assert result2.returncode == 0
        output2 = json.loads(result2.stdout)
        assert len(output2["sections"]) == 3
        assert "section-09-excel-writer.md" in output2["sections"]
        assert "section-08-calculator.md" not in output2["sections"]  # complete

    # Test 6: Batch numbers stay consistent
    def test_batch_numbers_consistent_with_partial_completion(self, run_script, tmp_path, twelve_section_index):
        """Batch numbers should be based on all sections, not just missing ones."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        # Complete all of batch 1
        batch1_sections = [
            "section-01-foundation", "section-02-config", "section-03-parser",
            "section-04-categorizer", "section-05-asset-discovery", "section-06-validator",
            "section-07-depreciation",
        ]
        self._create_section_files(sections_dir, batch1_sections)

        # Batch 2 should still be batch 2 (not batch 1)
        result = run_script(planning_dir, batch_num=2)
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["batch_num"] == 2
        assert output["total_batches"] == 2
        # Section 8 should be in batch 2, not renumbered
        assert "section-08-calculator.md" in output["sections"]

    # Test 7: Re-running after partial failure
    def test_rerun_after_partial_failure(self, run_script, tmp_path, twelve_section_index):
        """Re-running batch should only generate prompts for still-missing sections."""
        planning_dir = tmp_path / "planning"
        planning_dir.mkdir()
        sections_dir = planning_dir / "sections"
        sections_dir.mkdir()
        (sections_dir / "index.md").write_text(twelve_section_index)

        # First run: batch 1 with no sections
        result1 = run_script(planning_dir, batch_num=1)
        output1 = json.loads(result1.stdout)
        assert len(output1["sections"]) == 7

        # Simulate partial success: create 5 sections
        partial_sections = [
            "section-01-foundation", "section-02-config", "section-03-parser",
            "section-04-categorizer", "section-05-asset-discovery",
        ]
        self._create_section_files(sections_dir, partial_sections)

        # Second run: should only have 2 missing sections
        result2 = run_script(planning_dir, batch_num=1)
        assert result2.returncode == 0
        output2 = json.loads(result2.stdout)
        assert len(output2["sections"]) == 2
        assert "section-06-validator.md" in output2["sections"]
        assert "section-07-depreciation.md" in output2["sections"]
        # Completed sections should NOT be present
        assert "section-01-foundation.md" not in output2["sections"]
