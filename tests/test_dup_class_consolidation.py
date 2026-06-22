"""Tests for DUP fix: verify ConflictInfo and CurrentTask are not duplicated.

These tests ensure that:
- ConflictInfo is defined only in task_storage.py (canonical home)
- CurrentTask is defined only in task_storage.py (canonical home)
- task_reconciliation.py imports both from task_storage (no local definitions)
- No circular imports exist between the two modules
"""

import inspect
from pathlib import Path


def test_task_storage_exports_conflict_info():
    """from scripts.lib.task_storage import ConflictInfo should succeed."""
    from scripts.lib.task_storage import ConflictInfo
    assert ConflictInfo is not None


def test_task_storage_exports_current_task():
    """from scripts.lib.task_storage import CurrentTask should succeed."""
    from scripts.lib.task_storage import CurrentTask
    assert CurrentTask is not None


def test_task_reconciliation_imports_conflict_info():
    """from scripts.lib.task_reconciliation import ConflictInfo should succeed (via re-export)."""
    from scripts.lib.task_reconciliation import ConflictInfo
    assert ConflictInfo is not None


def test_task_reconciliation_imports_current_task():
    """from scripts.lib.task_reconciliation import CurrentTask should succeed (via re-export)."""
    from scripts.lib.task_reconciliation import CurrentTask
    assert CurrentTask is not None


def test_task_reconciliation_no_local_conflict_info_class():
    """task_reconciliation module should NOT define ConflictInfo class body (only imports it)."""
    source_path = Path(__file__).parent.parent / "scripts" / "lib" / "task_reconciliation.py"
    source = source_path.read_text()
    # Should not have a class definition for ConflictInfo
    assert "class ConflictInfo" not in source, (
        "task_reconciliation.py still defines ConflictInfo locally — "
        "it should import from task_storage instead"
    )


def test_task_reconciliation_no_local_current_task_class():
    """task_reconciliation module should NOT define CurrentTask class body (only imports it)."""
    source_path = Path(__file__).parent.parent / "scripts" / "lib" / "task_reconciliation.py"
    source = source_path.read_text()
    # Should not have a class definition for CurrentTask
    assert "class CurrentTask" not in source, (
        "task_reconciliation.py still defines CurrentTask locally — "
        "it should import from task_storage instead"
    )


def test_no_circular_import():
    """task_storage.py must NOT import from task_reconciliation (no circular dependency)."""
    source_path = Path(__file__).parent.parent / "scripts" / "lib" / "task_storage.py"
    source = source_path.read_text()
    # Check for actual import statements, not mentions in comments/docstrings
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue
        assert "import" not in stripped or "task_reconciliation" not in stripped, (
            f"task_storage.py imports from task_reconciliation — this creates a circular dependency: {stripped}"
        )


def test_classes_originate_from_task_storage():
    """ConflictInfo and CurrentTask in task_reconciliation should originate from task_storage.

    Note: Due to Python's import path mechanics (scripts.lib vs lib), the exact
    class objects may differ, but both should be defined in task_storage.py.
    """
    from scripts.lib.task_reconciliation import ConflictInfo as ReconConflictInfo
    from scripts.lib.task_reconciliation import CurrentTask as ReconCurrentTask

    # Both classes should trace back to task_storage (regardless of import path prefix)
    assert "task_storage" in ReconConflictInfo.__module__, (
        f"ConflictInfo in task_reconciliation should originate from task_storage, "
        f"but its module is {ReconConflictInfo.__module__}"
    )
    assert "task_storage" in ReconCurrentTask.__module__, (
        f"CurrentTask in task_reconciliation should originate from task_storage, "
        f"but its module is {ReconCurrentTask.__module__}"
    )
