"""Tests for concern tag support in parse_manifest_block()."""

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib.sections import parse_manifest_block


class TestManifestWithConcernTags:
    """Tests for concern tag parsing in SECTION_MANIFEST."""

    def test_manifest_with_concern_tags(self):
        """Should parse sections and extract concern tags."""
        content = """<!-- SECTION_MANIFEST
section-01-init scaffold
section-02-models functional
section-03-api functional
END_MANIFEST -->"""
        result = parse_manifest_block(content)
        assert result["success"] is True
        assert result["sections"] == [
            "section-01-init",
            "section-02-models",
            "section-03-api",
        ]
        assert result["section_concerns"] == {
            "section-01-init": "scaffold",
            "section-02-models": "functional",
            "section-03-api": "functional",
        }

    def test_manifest_without_tags(self):
        """Existing behavior preserved — no tags, no concerns."""
        content = """<!-- SECTION_MANIFEST
section-01-init
section-02-models
END_MANIFEST -->"""
        result = parse_manifest_block(content)
        assert result["success"] is True
        assert result["sections"] == ["section-01-init", "section-02-models"]
        assert result["section_concerns"] == {}

    def test_manifest_invalid_concern_tag(self):
        """Invalid tags produce a warning but don't fail."""
        content = """<!-- SECTION_MANIFEST
section-01-init scaffold
section-02-models bogus_concern
section-03-api functional
END_MANIFEST -->"""
        result = parse_manifest_block(content)
        assert result["success"] is True
        assert len(result["sections"]) == 3
        # Invalid tag not in concerns
        assert "section-02-models" not in result["section_concerns"]
        # Valid tags present
        assert result["section_concerns"]["section-01-init"] == "scaffold"
        assert result["section_concerns"]["section-03-api"] == "functional"
        # Warning generated
        assert any("bogus_concern" in w for w in result["warnings"])

    def test_manifest_mixed_tags(self):
        """Some lines tagged, some not — both parse correctly."""
        content = """<!-- SECTION_MANIFEST
section-01-init scaffold
section-02-models
section-03-api functional
section-04-tests
END_MANIFEST -->"""
        result = parse_manifest_block(content)
        assert result["success"] is True
        assert len(result["sections"]) == 4
        assert result["section_concerns"] == {
            "section-01-init": "scaffold",
            "section-03-api": "functional",
        }

    def test_all_six_concern_types(self):
        """All valid concern types are accepted."""
        content = """<!-- SECTION_MANIFEST
section-01-init scaffold
section-02-core functional
section-03-logging observability
section-04-config configuration
section-05-errors resilience
section-06-wiring integration
END_MANIFEST -->"""
        result = parse_manifest_block(content)
        assert result["success"] is True
        assert len(result["section_concerns"]) == 6

    def test_error_returns_include_section_concerns(self):
        """Error returns should have section_concerns key for consistent access."""
        # Missing manifest
        result = parse_manifest_block("# No manifest here")
        assert result["section_concerns"] == {}

        # Empty manifest
        result = parse_manifest_block("<!-- SECTION_MANIFEST\nEND_MANIFEST -->")
        assert result["section_concerns"] == {}
