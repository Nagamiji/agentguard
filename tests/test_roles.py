"""Pure-function tests for the RBAC scope helpers — no DB, always run.

The delegation boundary (`undelegatable_scopes`) is a security primitive: it decides
whether one key may mint another. Test its wildcard-aware semantics directly, so the
guarantee holds independent of the HTTP layer.
"""

from keel.roles import ROLE_SCOPES, scopes_for_role, undelegatable_scopes


def test_wildcard_creator_can_delegate_anything() -> None:
    # A creator holding '*' can grant any scope, including '*' itself.
    assert undelegatable_scopes(["*"], ["read", "write", "scan", "admin"]) == []
    assert undelegatable_scopes(["*"], ["*"]) == []


def test_non_wildcard_creator_cannot_grant_wildcard() -> None:
    # An admin key (no '*') cannot mint an owner/'*' key it does not itself hold.
    assert undelegatable_scopes(["read", "write", "scan", "admin"], ["*"]) == ["*"]


def test_subset_is_delegatable_superset_is_not() -> None:
    creator = ["read", "scan"]
    assert undelegatable_scopes(creator, ["read"]) == []
    assert undelegatable_scopes(creator, ["read", "scan"]) == []
    # 'write' is not held -> not delegatable; order preserved, only the excess reported.
    assert undelegatable_scopes(creator, ["read", "write"]) == ["write"]


def test_empty_request_is_always_delegatable() -> None:
    assert undelegatable_scopes(["read"], []) == []


def test_owner_role_expands_to_wildcard() -> None:
    # Sanity: role='owner' is exactly the wildcard the delegation boundary guards.
    assert scopes_for_role("owner") == ["*"]
    assert ROLE_SCOPES["admin"] == ["read", "write", "scan", "admin"]
