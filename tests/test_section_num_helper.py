"""Test the _section_num helper function for null-safe regex extraction."""

from scripts.lib.sections import _section_num


class TestSectionNumHelper:
    """Tests for the _section_num helper that safely extracts section numbers."""

    def test_valid_section_name(self):
        assert _section_num("section-05-foo") == 5

    def test_valid_section_double_digit(self):
        assert _section_num("section-12-bar-baz") == 12

    def test_non_matching_name_returns_zero(self):
        assert _section_num("not-a-section-file") == 0

    def test_empty_string_returns_zero(self):
        assert _section_num("") == 0

    def test_sort_with_non_matching_names(self):
        """Sorting a list containing non-matching names doesn't crash."""
        names = ["section-03-c", "bad-name", "section-01-a", "section-02-b"]
        sorted_names = sorted(names, key=_section_num)
        # bad-name gets 0, so it sorts first
        assert sorted_names[0] == "bad-name"
        assert sorted_names[1] == "section-01-a"

    def test_section_prefix_only(self):
        """Just 'section-01' without a name part still extracts number."""
        assert _section_num("section-01") == 1

    def test_single_digit(self):
        """Single digit section number works."""
        assert _section_num("section-3-name") == 3
