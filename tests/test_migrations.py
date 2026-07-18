"""Migration round-trip tests (unit level — no real DB required).

Verifies that every Alembic migration file:
- Has a valid revision and down_revision
- Has both upgrade() and downgrade() functions
- Is reachable (not orphaned in the chain)

Integration-level DB round-trip is performed in .github/workflows/migration-test.yml.
"""

import importlib
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations" / "versions"


def _load_migration(path: Path) -> object:
    """Dynamically import a migration module."""
    spec_name = f"migrations.{path.stem}"
    spec = importlib.util.spec_from_file_location(spec_name, path)
    if spec is None or spec.loader is None:
        pytest.fail(f"Could not load migration spec from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def get_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.py"))


@pytest.mark.parametrize("migration_file", get_migration_files())
def test_migration_has_revision(migration_file: Path) -> None:
    """Every migration must declare a revision ID string."""
    mod = _load_migration(migration_file)
    assert hasattr(mod, "revision"), f"{migration_file.name}: missing 'revision'"
    assert isinstance(mod.revision, str) and len(mod.revision) > 0


@pytest.mark.parametrize("migration_file", get_migration_files())
def test_migration_has_upgrade_and_downgrade(migration_file: Path) -> None:
    """Every migration must have both upgrade() and downgrade() functions."""
    mod = _load_migration(migration_file)
    assert hasattr(mod, "upgrade") and callable(mod.upgrade), (
        f"{migration_file.name}: missing upgrade()"
    )
    assert hasattr(mod, "downgrade") and callable(mod.downgrade), (
        f"{migration_file.name}: missing downgrade()"
    )


def test_migration_chain_has_no_orphans() -> None:
    """The down_revision chain must be connected — no file references a missing revision."""
    revisions: dict[str, str | None] = {}
    for path in get_migration_files():
        mod = _load_migration(path)
        rev = mod.revision  # type: ignore[attr-defined]
        down = getattr(mod, "down_revision", None)
        revisions[rev] = down

    # Every down_revision (except None = initial) must point to a known revision
    all_revs = set(revisions.keys())
    for rev, down in revisions.items():
        if down is not None:
            assert down in all_revs, (
                f"Migration '{rev}' references down_revision '{down}' "
                "which does not exist — orphaned migration chain!"
            )


def test_migration_count_matches_expectations() -> None:
    """Sanity: we should have at least 8 migrations after Phase 11."""
    files = get_migration_files()
    assert len(files) >= 8, (
        f"Expected at least 8 migration files, found {len(files)}. "
        "Did a migration accidentally get deleted?"
    )
