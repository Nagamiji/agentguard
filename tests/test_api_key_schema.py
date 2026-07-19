"""Unit tests for ApiKeyCreate scope normalisation (keel/schemas.py). No DB needed."""

import pytest
from pydantic import ValidationError

from keel.schemas import ApiKeyCreate


def test_duplicate_scopes_are_deduplicated_preserving_order() -> None:
    key = ApiKeyCreate(name="k", scopes=["read", "read", "write"])
    assert key.scopes == ["read", "write"]


def test_dedup_keeps_first_seen_order() -> None:
    key = ApiKeyCreate(name="k", scopes=["write", "read", "write", "read", "scan"])
    assert key.scopes == ["write", "read", "scan"]


def test_dedup_does_not_mask_invalid_scopes() -> None:
    with pytest.raises(ValidationError, match="Invalid scope"):
        ApiKeyCreate(name="k", scopes=["read", "read", "bogus"])


def test_empty_scopes_still_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        ApiKeyCreate(name="k", scopes=[])


def test_single_scope_unchanged() -> None:
    assert ApiKeyCreate(name="k", scopes=["admin"]).scopes == ["admin"]
