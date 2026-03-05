"""Tests for M3 fix: verify confused comments are replaced with clear ones."""

from pathlib import Path


def test_no_confused_phrases_in_generate_section_tasks():
    """Lines near the position mapping in generate-section-tasks.py should NOT contain
    stream-of-consciousness phrases like 'Actually', 'No wait', or 'Let me check'."""
    source_path = (
        Path(__file__).parent.parent
        / "scripts"
        / "checks"
        / "generate-section-tasks.py"
    )
    source = source_path.read_text()

    confused_phrases = ["Actually", "No wait", "Let me check", "wait no"]
    for phrase in confused_phrases:
        assert phrase not in source, (
            f"generate-section-tasks.py still contains confused phrase: '{phrase}'"
        )


def test_clear_position_documentation():
    """Comments near semantic_to_position assignments should explain the mapping formula."""
    source_path = (
        Path(__file__).parent.parent
        / "scripts"
        / "checks"
        / "generate-section-tasks.py"
    )
    source = source_path.read_text()

    # Find the block around the semantic_to_position assignments
    lines = source.splitlines()
    mapping_lines = []
    for i, line in enumerate(lines):
        if 'semantic_to_position["create-section-index"]' in line:
            # Grab a window of comment lines above this assignment
            start = max(0, i - 10)
            mapping_lines = lines[start : i + 1]
            break

    mapping_block = "\n".join(mapping_lines)
    # Should contain the position formula explanation
    assert "step" in mapping_block.lower() and "position" in mapping_block.lower(), (
        "Position mapping comments should explain the step-to-position formula"
    )
    # Should reference SECTION_INSERT_POSITION
    assert "SECTION_INSERT_POSITION" in mapping_block, (
        "Position mapping comments should reference SECTION_INSERT_POSITION"
    )
