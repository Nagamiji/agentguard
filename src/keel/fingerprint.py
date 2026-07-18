"""Backend re-export of the input-fingerprint implementation.

The canonical implementation now lives in ``agentguard_cli.fingerprint`` so that the public
``agentguard`` CLI wheel is self-contained and does not drag in the ``keel`` backend package
(see docs/architecture/be-02-agent-registry.md and the PyPI packaging split). The backend
image ships both packages, so it re-exports the identical code here — there is exactly one
implementation, and every historical fingerprint is preserved byte-for-byte.

Importers inside the backend keep using ``from keel.fingerprint import ...`` unchanged.
"""

from __future__ import annotations

from agentguard_cli.fingerprint import (
    BEHAVIOURAL_FIELDS,
    EXCLUDED_FIELDS,
    FINGERPRINT_ALGO,
    MAX_DEPTH,
    ManifestError,
    canonical_manifest,
    compute_fingerprint,
    find_secrets,
)

__all__ = [
    "BEHAVIOURAL_FIELDS",
    "EXCLUDED_FIELDS",
    "FINGERPRINT_ALGO",
    "MAX_DEPTH",
    "ManifestError",
    "canonical_manifest",
    "compute_fingerprint",
    "find_secrets",
]
