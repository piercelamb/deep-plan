"""Shared section-checking logic for deep-plan plugin.

Used by both setup-planning-session.py and check-sections.py.
"""

import re
from pathlib import Path


# Section name pattern: section-NN-name (name is required, at least one char)
SECTION_NAME_PATTERN = re.compile(r'^section-(\d{2})-([a-zA-Z0-9_-]+)$')

# Manifest block markers
MANIFEST_START = '<!-- SECTION_MANIFEST'
MANIFEST_END = 'END_MANIFEST -->'


def _section_num(name: str) -> int:
    """Extract section number for sorting. Returns 0 if pattern doesn't match."""
    m = re.search(r'section-(\d+)', name)
    return int(m.group(1)) if m else 0


def parse_manifest_block(content: str) -> dict:
    """Parse the SECTION_MANIFEST block from index.md content.

    Expected format:
    <!-- SECTION_MANIFEST
    section-01-foundation
    section-02-config
    section-03-parser
    END_MANIFEST -->

    Args:
        content: Full content of index.md

    Returns:
        dict with:
        - success: bool
        - sections: list of section names (empty if failed)
        - error: error message if failed, None otherwise
        - warnings: list of warning messages
    """
    warnings = []

    # Find manifest block
    start_idx = content.find(MANIFEST_START)
    if start_idx == -1:
        return {
            "success": False,
            "sections": [],
            "error": "No SECTION_MANIFEST block found in index.md. "
                     "index.md must start with a SECTION_MANIFEST block. "
                     "See SKILL.md step 18 for the required format.",
            "warnings": warnings,
        }

    end_idx = content.find(MANIFEST_END, start_idx)
    if end_idx == -1:
        return {
            "success": False,
            "sections": [],
            "error": "SECTION_MANIFEST block not closed (missing END_MANIFEST -->)",
            "warnings": warnings,
        }

    # Extract content between markers
    block_start = start_idx + len(MANIFEST_START)
    block_content = content[block_start:end_idx].strip()

    if not block_content:
        return {
            "success": False,
            "sections": [],
            "error": "SECTION_MANIFEST block is empty. Add section definitions, one per line.",
            "warnings": warnings,
        }

    # Parse lines
    sections = []
    seen_numbers = set()

    for line_num, line in enumerate(block_content.split('\n'), start=1):
        line = line.strip()
        if not line:
            continue  # Skip empty lines

        # Validate section name format
        match = SECTION_NAME_PATTERN.match(line)
        if not match:
            return {
                "success": False,
                "sections": [],
                "error": f"Invalid section name on line {line_num}: '{line}'. "
                         f"Expected format: section-NN-name (e.g., section-01-foundation). "
                         f"Section numbers must be two digits (01, 02, etc.).",
                "warnings": warnings,
            }

        section_num = match.group(1)
        if section_num in seen_numbers:
            return {
                "success": False,
                "sections": [],
                "error": f"Duplicate section number on line {line_num}: '{line}'. "
                         f"Section {section_num} already defined.",
                "warnings": warnings,
            }

        seen_numbers.add(section_num)
        sections.append(line)

    if not sections:
        return {
            "success": False,
            "sections": [],
            "error": "No valid sections found in SECTION_MANIFEST block",
            "warnings": warnings,
        }

    # Sort by section number
    sections.sort(key=_section_num)

    # Validate sequential numbering (warn if gaps)
    expected_num = 1
    for section in sections:
        match = SECTION_NAME_PATTERN.match(section)
        if not match:
            continue
        actual_num = int(match.group(1))
        if actual_num != expected_num:
            warnings.append(
                f"Section numbering gap: expected section-{expected_num:02d}, "
                f"found section-{actual_num:02d}"
            )
        expected_num = actual_num + 1

    return {
        "success": True,
        "sections": sections,
        "error": None,
        "warnings": warnings,
    }


def parse_index_sections(index_path: Path) -> list[str]:
    """Extract section names from index.md SECTION_MANIFEST block.

    This function requires a valid SECTION_MANIFEST block. If the block
    is missing or invalid, returns an empty list. Use check_index_format()
    to get detailed error information.

    Args:
        index_path: Path to sections/index.md

    Returns:
        List of section names sorted by number, or empty list if invalid.
    """
    if not index_path.exists():
        return []

    content = index_path.read_text()
    result = parse_manifest_block(content)

    if result["success"]:
        return result["sections"]

    # No fallback - return empty list if manifest is invalid
    return []


def check_index_format(index_path: Path) -> dict:
    """Check the format of index.md and return detailed status.

    This is the primary validation function. Use this to get error details
    when parse_index_sections() returns an empty list.

    Args:
        index_path: Path to sections/index.md

    Returns:
        dict with:
        - exists: bool - whether index.md exists
        - has_manifest: bool - whether SECTION_MANIFEST block exists
        - manifest_valid: bool - whether manifest block is valid
        - sections: list of section names (empty if invalid)
        - error: error message if manifest is invalid
        - warnings: list of warnings
    """
    if not index_path.exists():
        return {
            "exists": False,
            "has_manifest": False,
            "manifest_valid": False,
            "sections": [],
            "error": "index.md does not exist",
            "warnings": [],
        }

    content = index_path.read_text()

    # Check for manifest block
    has_manifest = MANIFEST_START in content

    if not has_manifest:
        return {
            "exists": True,
            "has_manifest": False,
            "manifest_valid": False,
            "sections": [],
            "error": "index.md is missing SECTION_MANIFEST block. "
                     "index.md must start with a SECTION_MANIFEST block. "
                     "See SKILL.md step 18 for the required format.",
            "warnings": [],
        }

    # Parse the manifest block
    result = parse_manifest_block(content)
    return {
        "exists": True,
        "has_manifest": True,
        "manifest_valid": result["success"],
        "sections": result["sections"],
        "error": result["error"],
        "warnings": result["warnings"],
    }


def get_completed_sections(sections_dir: Path) -> list[str]:
    """Get list of completed section files (without .md extension).

    Args:
        sections_dir: Path to sections/ directory

    Returns:
        List of section names sorted by number (e.g., ["section-01-setup", "section-02-api"])
    """
    if not sections_dir.exists():
        return []

    completed = []
    for f in sections_dir.glob("section-*.md"):
        # Remove .md extension
        completed.append(f.stem)

    # Sort by section number
    completed.sort(key=_section_num)

    return completed


def check_section_progress(planning_dir: Path) -> dict:
    """Check section-splitting progress.

    Args:
        planning_dir: Path to planning directory

    Returns:
        dict with:
        - state: "fresh" | "has_index" | "partial" | "complete" | "invalid_index"
        - index_exists: bool
        - defined_sections: list of section names from index.md
        - completed_sections: list of completed section file names
        - missing_sections: list of sections not yet written
        - next_section: name of next section to write (or None)
        - progress: string like "2/12"
        - index_format: dict with format validation details (from check_index_format)
    """
    sections_dir = planning_dir / "sections"
    index_path = sections_dir / "index.md"

    sections_dir_exists = sections_dir.exists() and sections_dir.is_dir()
    index_exists = index_path.exists()

    # Get format validation details
    if index_exists:
        index_format = check_index_format(index_path)
    else:
        index_format = {
            "exists": False,
            "has_manifest": False,
            "manifest_valid": False,
            "sections": [],
            "error": None,
            "warnings": [],
        }

    defined_sections = index_format["sections"]
    completed_sections = get_completed_sections(sections_dir) if sections_dir_exists else []

    # Calculate missing sections
    completed_set = set(completed_sections)
    missing_sections = [s for s in defined_sections if s not in completed_set]

    # Determine state
    if not sections_dir_exists or (not index_exists and not completed_sections):
        state = "fresh"
    elif index_exists and not index_format["manifest_valid"]:
        # index.md exists but SECTION_MANIFEST is missing or invalid
        state = "invalid_index"
    elif index_exists and not completed_sections:
        state = "has_index"
    elif index_exists and missing_sections:
        state = "partial"
    elif index_exists and not missing_sections and defined_sections:
        state = "complete"
    else:
        state = "fresh"

    next_section = missing_sections[0] if missing_sections else None

    total = len(defined_sections)
    done = len(completed_sections)
    progress = f"{done}/{total}" if total > 0 else "0/0"

    return {
        "state": state,
        "index_exists": index_exists,
        "defined_sections": defined_sections,
        "completed_sections": completed_sections,
        "missing_sections": missing_sections,
        "next_section": next_section,
        "progress": progress,
        "index_format": index_format,
    }
