"""Verdict signing — an HMAC over the gate decision (Phase 5)."""

import pytest

from keel import signing
from keel.config import settings


def test_signing_is_disabled_without_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "signing_secret", "")
    assert signing.sign_verdict("fp", "blocked", "run1") is None
    assert signing.verify_verdict("anything", "fp", "blocked") is False


def test_a_signature_verifies_and_is_tamper_evident(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "signing_secret", "s3kr3t")
    sig = signing.sign_verdict("fp", "allowed", "run1")
    assert sig and len(sig) == 64

    assert signing.verify_verdict(sig, "fp", "allowed", "run1")
    # Any change to the verdict invalidates the signature.
    assert not signing.verify_verdict(sig, "fp", "blocked", "run1")
    assert not signing.verify_verdict(sig, "OTHER", "allowed", "run1")


def test_a_different_secret_produces_a_different_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "signing_secret", "key-a")
    a = signing.sign_verdict("fp", "allowed")
    monkeypatch.setattr(settings, "signing_secret", "key-b")
    b = signing.sign_verdict("fp", "allowed")
    assert a != b
