"""The CLI computes fingerprints locally and must agree with the server byte-for-byte.

`agentguard` ships as a standalone distribution that must not import the server package, so
`agentguard_core/fingerprint.py` is a copy of `keel/fingerprint.py`. A divergence would let
the CLI attach a verdict to a different configuration than the server evaluated — a silent
correctness hole. This guard fails CI the moment the two files differ; update both together
(or promote the module to a shared distribution).
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER = _REPO_ROOT / "src" / "keel" / "fingerprint.py"
_CLI = _REPO_ROOT / "cli" / "src" / "agentguard_core" / "fingerprint.py"


def test_cli_fingerprint_is_identical_to_server() -> None:
    assert _SERVER.is_file() and _CLI.is_file()
    assert _CLI.read_bytes() == _SERVER.read_bytes(), (
        "cli/src/agentguard_core/fingerprint.py has drifted from src/keel/fingerprint.py; "
        "update both together — the CLI and server must compute identical fingerprints."
    )


def test_cli_and_server_compute_the_same_fingerprint() -> None:
    """Behavioural backstop: identical bytes should of course fingerprint identically, but
    assert it through both import paths so a packaging mistake can't hide a mismatch."""
    from agentguard_core.fingerprint import compute_fingerprint as cli_fp
    from keel.fingerprint import compute_fingerprint as server_fp

    manifest = {
        "prompts": [{"role": "system", "content": "You are a refund agent."}],
        "model": {"provider": "anthropic", "id": "claude-opus-4-8-20260115"},
        "tools": [{"name": "issue_refund"}],
        "params": {"temperature": 0.2},
    }
    assert cli_fp(manifest) == server_fp(manifest)
