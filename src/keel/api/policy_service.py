"""Resolve + compile the effective policy for an agent.

The DB-querying orchestration lives here (not in `keel.policy`, which stays pure) because
two routers need it: the policy preview endpoint and the eval run. Sharing it means the
policy a customer previews is byte-for-byte the policy a scan enforces.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.models import Policy, PolicyVersion
from keel.policy import CompiledPolicy, ResolvedRule, compile_policy, resolve
from keel.policy.resolver import effective_values


def _latest_rules(
    db: Session, scope_type: str, scope_id: uuid.UUID, environment: str | None
) -> dict[str, Any] | None:
    """The rules of the newest version of the policy at this exact (scope, environment), or
    None if there is no such policy."""
    condition = (
        Policy.environment.is_(None) if environment is None else Policy.environment == environment
    )
    policy = db.execute(
        select(Policy).where(
            Policy.scope_type == scope_type,
            Policy.scope_id == scope_id,
            condition,
        )
    ).scalar_one_or_none()
    if policy is None:
        return None
    version = db.execute(
        select(PolicyVersion)
        .where(PolicyVersion.policy_id == policy.id)
        .order_by(PolicyVersion.sequence_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    return version.rules if version is not None else None


def build_layers(
    db: Session, org_id: uuid.UUID, agent_id: uuid.UUID, environment: str | None
) -> list[tuple[str, dict[str, Any]]]:
    """Applicable policies, lowest precedence first, for the resolver.

    Order: organization (agnostic, then env-specific), then agent (agnostic, then
    env-specific). Later wins, so env-specific overrides agnostic within a scope, and agent
    overrides organization across scopes. (Project scope is intentionally absent — agents
    are not linked to projects yet; ADR 0012.)
    """
    layers: list[tuple[str, dict[str, Any]]] = []
    for label, scope_type, scope_id in (
        ("organization", "organization", org_id),
        ("agent", "agent", agent_id),
    ):
        agnostic = _latest_rules(db, scope_type, scope_id, None)
        if agnostic:
            layers.append((label, agnostic))
        if environment is not None:
            specific = _latest_rules(db, scope_type, scope_id, environment)
            if specific:
                layers.append((label, specific))
    return layers


def effective_policy(
    db: Session,
    org_id: uuid.UUID,
    agent_id: uuid.UUID,
    environment: str | None,
    manifest: dict[str, Any],
) -> tuple[dict[str, ResolvedRule], CompiledPolicy]:
    """Resolve precedence and compile against the manifest. Empty resolved == no policy."""
    layers = build_layers(db, org_id, agent_id, environment)
    resolved = resolve(layers)
    compiled = compile_policy(effective_values(resolved), manifest)
    return resolved, compiled
