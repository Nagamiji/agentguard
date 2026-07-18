"""Regression guard for the Auto Merge workflow.

PRs #12 and #13 landed on `main` with red checks because the original workflow used
GitHub's native `gh pr merge --auto`, which — without branch protection (unavailable on
this plan, see docs/branch-protection.md) — merges immediately regardless of check status.
PR #14 replaced it with a workflow that inspects the PR head's check runs and merges only
when they are green.

This test fails if anyone reintroduces the footgun. It reads no secrets and needs no DB,
so it runs in the `unit` gate. It is deliberately text-based (not a YAML/behavioural test):
the property we protect is "the executed merge command never opts into instant auto-merge,
and the merge is gated on check runs."
"""

from pathlib import Path

_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "auto-merge.yml"


def _executable_lines(text: str) -> list[str]:
    """Lines that are not comments. Covers both YAML `#` comments and shell `#` comments
    inside the run: block — the workflow's own docstring legitimately names `--auto`."""
    out = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(raw)
    return out


def test_auto_merge_workflow_exists() -> None:
    assert _WORKFLOW.is_file(), f"{_WORKFLOW} is missing — the merge gate must exist"


def test_no_native_instant_auto_merge() -> None:
    """The executed `gh pr merge` must never use --auto (instant merge, ignores checks)."""
    lines = _executable_lines(_WORKFLOW.read_text())
    merge_lines = [ln for ln in lines if "gh pr merge" in ln]
    assert merge_lines, "expected the workflow to merge via `gh pr merge`"
    offenders = [ln for ln in merge_lines if "--auto" in ln]
    assert not offenders, (
        "Auto Merge must not use `gh pr merge --auto`: without branch protection it merges "
        f"instantly, red or green (see PRs #12/#13). Offending line(s): {offenders}"
    )


def test_merge_is_gated_on_check_runs() -> None:
    """The workflow must actually inspect check runs before merging."""
    body = "\n".join(_executable_lines(_WORKFLOW.read_text()))
    assert "check-runs" in body, "the merge must be gated on the PR head's check runs"
    # The two required gates must be named, so a missing check cannot read as a pass.
    assert "gate" in body
    assert "Migration round-trip" in body


def test_merge_requires_the_ready_to_merge_label() -> None:
    """A human applying the label is the maker != checker gate (CLAUDE.md)."""
    body = "\n".join(_executable_lines(_WORKFLOW.read_text()))
    assert "ready-to-merge" in body
