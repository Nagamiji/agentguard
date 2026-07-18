"""RBAC roles as named presets over the flat scope vocabulary.

Scopes are the enforcement primitive (`keel/deps.py` checks them); a *role* is just a
human-friendly bundle of scopes chosen at key-creation time. Keeping enforcement on the
scopes — not the role name — means a verdict stays explainable at 2am ("key lacks
'write'") and a role rename can never silently widen access.

The scope vocabulary is intentionally small and orthogonal:
  read   — list/get any tenant resource
  write  — create/update/delete agents, versions, scenarios, policies, projects
  scan   — run evaluations and read their gate/risk verdicts
  admin  — manage API keys and organization lifecycle
  *      — everything (the org's first bootstrap key; the `owner` role)
"""

VALID_SCOPES: frozenset[str] = frozenset({"*", "read", "write", "scan", "admin"})

# Ordered loosely most- to least-privileged for display; enforcement never relies on order.
ROLE_SCOPES: dict[str, list[str]] = {
    "owner": ["*"],
    "admin": ["read", "write", "scan", "admin"],
    "developer": ["read", "write", "scan"],
    # The flagship scoped-key use case: a CI/GitHub-Actions key that can run scans and
    # read verdicts but cannot touch agents, keys, or org settings.
    "ci": ["read", "scan"],
    "viewer": ["read"],
}

VALID_ROLES: frozenset[str] = frozenset(ROLE_SCOPES)


def scopes_for_role(role: str) -> list[str]:
    """Expand a role name into its scope list. Caller validates membership first."""
    return list(ROLE_SCOPES[role])
