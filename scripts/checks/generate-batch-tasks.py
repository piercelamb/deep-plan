#!/usr/bin/env python3
"""Generate prompt files for a batch of section-writing subagents.

This script:
1. Writes full prompt files to <planning_dir>/sections/.prompts/
2. Outputs JSON with the prompt file paths for Claude to use

Claude then launches parallel Task subagents, one per prompt file.

Usage:
    uv run generate-batch-tasks.py --planning-dir "/path/to/planning" --batch-num 1

Output:
    JSON with prompt_files array for Claude to launch Task calls.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_session_config, ConfigError
from lib.sections import check_section_progress
from lib.tasks import BATCH_SIZE


def load_prompt_template(plugin_root: Path) -> str:
    """Load the section writer prompt template.

    Args:
        plugin_root: Path to the plugin root directory

    Returns:
        The prompt template content

    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_path = plugin_root / "prompts" / "section_writer" / "prompt.md"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    return template_path.read_text().strip()


def fill_template(template: str, planning_dir: str, section_name: str) -> str:
    """Fill in the prompt template placeholders.

    Args:
        template: The prompt template with placeholders
        planning_dir: Path to the planning directory
        section_name: Section name without .md extension (e.g., "section-01-setup")

    Returns:
        Filled-in prompt ready for use
    """
    section_filename = f"{section_name}.md"

    return (
        template
        .replace("{PLANNING_DIR}", planning_dir)
        .replace("{SECTION_FILENAME}", section_filename)
        .replace("{SECTION_NAME}", section_name)
    )


def write_prompt_file(prompts_dir: Path, section_name: str, prompt_content: str) -> Path:
    """Write a prompt file for a section.

    Args:
        prompts_dir: Directory to write prompt files to
        section_name: Section name (e.g., "section-01-setup")
        prompt_content: The full prompt content

    Returns:
        Path to the written prompt file
    """
    prompt_file = prompts_dir / f"{section_name}-prompt.md"
    prompt_file.write_text(prompt_content)
    return prompt_file


def generate_batch_tasks(
    planning_dir: Path,
    batch_num: int,
    plugin_root: Path,
) -> dict:
    """Generate prompt files for all sections in the specified batch.

    Writes full prompts to files and returns paths for Claude to use.

    Args:
        planning_dir: Path to the planning directory
        batch_num: Which batch to generate (1-indexed)
        plugin_root: Path to the plugin root directory

    Returns:
        dict with:
        - success: bool
        - error: error message if failed
        - batch_num: the batch number
        - total_batches: total number of batches
        - sections: list of section filenames in this batch
        - prompt_files: list of prompt file paths written
        - message: optional message (e.g., "nothing to do")
    """
    # Check section progress
    progress = check_section_progress(planning_dir)

    if progress["state"] == "fresh":
        return {
            "success": False,
            "error": "No sections/index.md found. Create the section index first.",
            "batch_num": batch_num,
            "total_batches": 0,
            "sections": [],
            "prompt_files": [],
        }

    if progress["state"] == "invalid_index":
        error_msg = progress.get("index_format", {}).get("error", "Invalid index.md")
        return {
            "success": False,
            "error": f"Invalid index.md: {error_msg}",
            "batch_num": batch_num,
            "total_batches": 0,
            "sections": [],
            "prompt_files": [],
        }

    if progress["state"] == "complete":
        return {
            "success": True,
            "error": None,
            "batch_num": batch_num,
            "total_batches": 0,
            "sections": [],
            "prompt_files": [],
            "message": "All sections already written. Nothing to do.",
        }

    # Use defined_sections for batch calculation (consistent with TODO batch numbers)
    # but filter to only missing sections when generating tasks
    all_sections = progress["defined_sections"]
    missing_sections_set = set(progress.get("missing_sections", all_sections))

    if not all_sections:
        return {
            "success": False,
            "error": "No sections defined in index.md",
            "batch_num": batch_num,
            "total_batches": 0,
            "sections": [],
            "prompt_files": [],
        }

    # Calculate batches
    num_batches = (len(all_sections) + BATCH_SIZE - 1) // BATCH_SIZE

    if batch_num < 1 or batch_num > num_batches:
        return {
            "success": False,
            "error": f"Invalid batch number {batch_num}. Valid range: 1-{num_batches}",
            "batch_num": batch_num,
            "total_batches": num_batches,
            "sections": [],
            "prompt_files": [],
        }

    # Get sections for this batch
    start_idx = (batch_num - 1) * BATCH_SIZE
    end_idx = min(start_idx + BATCH_SIZE, len(all_sections))
    batch_sections_all = all_sections[start_idx:end_idx]

    # Filter to only missing sections (preserve order)
    batch_sections = [s for s in batch_sections_all if s in missing_sections_set]

    # If no missing sections in this batch, nothing to do
    if not batch_sections:
        return {
            "success": True,
            "error": None,
            "batch_num": batch_num,
            "total_batches": num_batches,
            "sections": [],
            "prompt_files": [],
            "message": f"Batch {batch_num} sections already written. Nothing to do.",
        }

    # Load prompt template
    try:
        template = load_prompt_template(plugin_root)
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "batch_num": batch_num,
            "total_batches": num_batches,
            "sections": batch_sections,
            "prompt_files": [],
        }

    # Create prompts directory
    prompts_dir = planning_dir / "sections" / ".prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # Write prompt files for each section
    prompt_files = []
    planning_dir_str = str(planning_dir.resolve())

    for section_name in batch_sections:
        # Write full prompt to file
        filled_prompt = fill_template(template, planning_dir_str, section_name)
        prompt_file = write_prompt_file(prompts_dir, section_name, filled_prompt)
        prompt_files.append(str(prompt_file))

    return {
        "success": True,
        "error": None,
        "batch_num": batch_num,
        "total_batches": num_batches,
        "sections": [f"{s}.md" for s in batch_sections],
        "prompt_files": prompt_files,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate prompt files for a batch of section-writing subagents"
    )
    parser.add_argument(
        "--planning-dir",
        required=True,
        type=Path,
        help="Path to planning directory"
    )
    parser.add_argument(
        "--batch-num",
        required=True,
        type=int,
        help="Batch number to generate (1-indexed)"
    )
    args = parser.parse_args()

    # Load session config to get plugin_root
    try:
        session_config = load_session_config(args.planning_dir)
    except ConfigError as e:
        result = {
            "success": False,
            "error": f"Session config not found: {e}",
            "batch_num": args.batch_num,
            "total_batches": 0,
            "sections": [],
            "prompt_files": [],
        }
        print(json.dumps(result, indent=2))
        return 1

    plugin_root = Path(session_config.get("plugin_root", ""))
    if not plugin_root.exists():
        result = {
            "success": False,
            "error": f"Plugin root not found: {plugin_root}",
            "batch_num": args.batch_num,
            "total_batches": 0,
            "sections": [],
            "prompt_files": [],
        }
        print(json.dumps(result, indent=2))
        return 1

    result = generate_batch_tasks(args.planning_dir, args.batch_num, plugin_root)

    # Always output JSON
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
