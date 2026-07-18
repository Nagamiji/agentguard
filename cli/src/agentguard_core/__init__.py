"""agentguard_core — logic shared by the CLI and, by contract, the server.

`fingerprint.py` is a byte-for-byte copy of `src/keel/fingerprint.py`. The CLI ships as a
standalone distribution and must not depend on the server package, but the fingerprint the
CLI computes locally MUST equal the one the server computes — a mismatch would attach a
verdict to the wrong configuration. `tests/test_cli_core_no_drift.py` fails CI if the two
files ever diverge; update both together.
"""

__version__ = "0.1.0"
