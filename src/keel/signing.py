"""Sign a gate verdict so a downstream consumer can confirm it was not tampered with.

Honest scope, because a security feature that overclaims is worse than none:

  * This is an **HMAC** keyed by a server secret. It proves a verdict was produced by a party
    holding that secret and has not been altered since. It is integrity + authenticity for
    anyone who trusts this server and holds the key.
  * It is **NOT** third-party non-repudiation. Anyone with the key can forge a signature, so
    it cannot prove to an untrusting outsider that *this* server signed it. That needs
    asymmetric signing (an Ed25519 keypair, public key published) — the documented upgrade.

The realistic use today: a deploy system or auditor that trusts AgentGuard verifies that a
"allowed" verdict carried in a pipeline artifact is genuine and matches the fingerprint it
claims. The CI runner itself is not the verifier (it already trusts the API response it got
over TLS + API key); it just carries the signed verdict forward.
"""

from __future__ import annotations

import hashlib
import hmac

from keel.config import settings


def _message(fingerprint: str, decision: str, run_id: str | None) -> bytes:
    # "run <run_id> produced <decision> for <fingerprint>". run_id pins the run (and thus its
    # timestamp) immutably, so no separate time field is needed — and including one would
    # only invite a serialization-format mismatch between signer and verifier.
    return f"{fingerprint}|{decision}|{run_id or ''}".encode()


def sign_verdict(fingerprint: str, decision: str, run_id: str | None = None) -> str | None:
    """Return a hex HMAC-SHA256 over the verdict, or None when signing is disabled."""
    if not settings.signing_secret:
        return None
    return hmac.new(
        settings.signing_secret.encode(),
        _message(fingerprint, decision, run_id),
        hashlib.sha256,
    ).hexdigest()


def verify_verdict(
    signature: str, fingerprint: str, decision: str, run_id: str | None = None
) -> bool:
    """Constant-time check that a signature matches a verdict (False if signing disabled)."""
    expected = sign_verdict(fingerprint, decision, run_id)
    if expected is None:
        return False
    return hmac.compare_digest(expected, signature)
