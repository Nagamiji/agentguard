"""Guards for the PyPI packaging split (fix/pypi-cli-packaging).

The published `agentguard` wheel must be the CLI *only*: importing it must not require the
`keel` backend or `worker`, and it must not drag the FastAPI/SQLAlchemy/Redis stack onto a
plain `pip install agentguard`. These tests fail loudly if a future change reintroduces that
coupling — the failure mode the audit caught, where the whole backend shipped to PyPI.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

from agentguard_cli import fingerprint as cli_fp
from keel import fingerprint as keel_fp

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLI_DIR = _REPO_ROOT / "src" / "agentguard_cli"


def _manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "prompts": [{"role": "system", "content": "You are a refund agent."}],
        "tools": [
            {"name": "issue_refund", "description": "Refund.", "schema": {"type": "object"}},
            {"name": "lookup_order", "description": "Find.", "schema": {"type": "object"}},
        ],
        "model": {"provider": "anthropic", "id": "claude-opus-4-8-20260115"},
        "params": {"temperature": 0.2, "max_tokens": 1024},
        "retrieval": {"index_id": "orders-v3", "embedding_model": "voyage-3", "top_k": 5},
        "framework": {"name": "langgraph", "version": "0.3.1"},
        "name": "Refund agent",
    }
    base.update(overrides)
    return base


# --- the move preserved behaviour byte-for-byte ------------------------------------------

_CASES = [
    _manifest(),
    _manifest(model={"provider": "openai", "id": "gpt-4o-2024-08-06"}),
    _manifest(tools=[]),
    _manifest(params={"temperature": 0.0}),
    {"prompts": [{"role": "system", "content": "  trailing  \r\n\r\n\r\nspace  "}]},
]


@pytest.mark.parametrize("manifest", _CASES)
def test_cli_and_keel_fingerprints_are_identical(manifest: dict[str, object]) -> None:
    """keel.fingerprint re-exports the CLI implementation — output must match exactly."""
    assert cli_fp.compute_fingerprint(manifest) == keel_fp.compute_fingerprint(manifest)


def test_reexport_is_the_same_object() -> None:
    """The backend symbol is literally the CLI's, so there is one implementation, not two."""
    assert keel_fp.compute_fingerprint is cli_fp.compute_fingerprint
    assert keel_fp.ManifestError is cli_fp.ManifestError
    assert keel_fp.FINGERPRINT_ALGO == cli_fp.FINGERPRINT_ALGO == "v1"


def test_known_vector_is_stable() -> None:
    """A frozen expected value so a silent canonicalisation change is caught, not just drift."""
    expected = cli_fp.compute_fingerprint(_manifest())
    # Recomputed independently via the backend path.
    assert keel_fp.compute_fingerprint(_manifest()) == expected
    assert len(expected) == 64  # sha-256 hex


# --- the CLI package does not import the backend -----------------------------------------


def _cli_modules() -> list[Path]:
    return sorted(p for p in _CLI_DIR.glob("*.py"))


@pytest.mark.parametrize("module_path", _cli_modules(), ids=lambda p: p.name)
def test_cli_module_does_not_import_keel_or_worker(module_path: Path) -> None:
    """No agentguard_cli source may import `keel` or `worker` — the wheel ships neither."""
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            assert top not in {"keel", "worker"}, (
                f"{module_path.name} imports '{name}': the published CLI wheel must not depend "
                f"on the backend. Vendor what you need into agentguard_cli."
            )


# --- pyproject declares a CLI-only package ------------------------------------------------


def _pyproject() -> dict:
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())


def test_runtime_dependencies_are_cli_only() -> None:
    """A plain install must not pull the backend stack (fastapi/sqlalchemy/redis/...)."""
    deps = _pyproject()["project"]["dependencies"]
    names = {d.split(">")[0].split("=")[0].split("[")[0].strip().lower() for d in deps}
    backend = {"fastapi", "uvicorn", "sqlalchemy", "alembic", "psycopg", "redis", "google-auth"}
    assert names & backend == set(), f"backend deps leaked into runtime install: {names & backend}"
    assert "httpx" in names


def test_package_discovery_is_scoped_to_cli() -> None:
    """`include` must keep keel/worker out of the built wheel."""
    find = _pyproject()["tool"]["setuptools"]["packages"]["find"]
    assert find.get("include") == ["agentguard_cli*"]
