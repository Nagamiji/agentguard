"""Policy rule taxonomy + write-time validation.

Two honest classes of rule:

  * DEPLOY_ENFORCED — things a deploy-time, simulate-don't-execute gate can actually check:
    the agent's declared config and what it tries to do in a scan. These compile into checks.
  * RUNTIME_DECLARED — things only observable in production: token spend over time, request
    rate, wall-clock latency, geography, time-of-day, human-in-the-loop approvals. A deploy
    gate CANNOT verify these; they belong to a runtime enforcement layer we do not yet have.
    We accept and store them (so the policy is complete and audited) but the compiler marks
    them deferred rather than pretending to enforce them.

Anything else is REJECTED at write time. Silently ignoring an unknown rule is the worst
outcome: a customer writes "max_refund: 100", typos the key, and believes they are protected
while the gate enforces nothing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# name -> a validator that raises PolicyError on a malformed value.
DEPLOY_ENFORCED = frozenset(
    {
        "max_tool_arg",  # [{tool, arg, max}] — e.g. issue_refund.amount <= 100
        "forbidden_tools",  # [str] — the agent must never call these
        "allowed_tools",  # [str] — the agent may ONLY call these (allow-list)
        "max_tool_calls",  # int — cap on tool calls in one interaction
        "allowed_providers",  # [str] — model provider must be one of these
        "allowed_model_families",  # [str] — model id must start with one of these
    }
)

# Accepted, stored, surfaced — but NOT enforced by the deploy gate. See module docstring.
RUNTIME_DECLARED = frozenset(
    {
        "max_token_budget",
        "rate_limit",
        "max_execution_time_seconds",
        "allowed_retrieval_sources",
        "human_approval_required",
        "geo_restrictions",
        "time_restrictions",
        "risk_threshold",
    }
)

KNOWN_RULES = DEPLOY_ENFORCED | RUNTIME_DECLARED


class PolicyError(ValueError):
    """A malformed policy. Surfaces to the caller as a 400 — never silently dropped."""


def _require_list_of_str(key: str, value: Any) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PolicyError(f"rule '{key}' must be a list of strings")


def _validate_max_tool_arg(value: Any) -> None:
    if not isinstance(value, list):
        raise PolicyError("rule 'max_tool_arg' must be a list of {tool, arg, max}")
    for entry in value:
        if not isinstance(entry, dict):
            raise PolicyError("each 'max_tool_arg' entry must be an object")
        for field in ("tool", "arg"):
            if not isinstance(entry.get(field), str):
                raise PolicyError(f"'max_tool_arg' entry needs a string '{field}'")
        limit = entry.get("max")
        if isinstance(limit, bool) or not isinstance(limit, int | float):
            raise PolicyError("'max_tool_arg' entry needs a numeric 'max'")


def validate_rules(rules: Any) -> None:
    """Reject an unknown or malformed rule at write time."""
    if not isinstance(rules, dict):
        raise PolicyError("policy rules must be an object")
    if not rules:
        raise PolicyError("a policy must declare at least one rule")

    for key, value in rules.items():
        if key not in KNOWN_RULES:
            raise PolicyError(
                f"unknown rule '{key}'. Known rules: {', '.join(sorted(KNOWN_RULES))}"
            )
        if value is None:
            # An explicit null clears a rule at this scope; always allowed.
            continue
        if key == "max_tool_arg":
            _validate_max_tool_arg(value)
        elif key in (
            "forbidden_tools",
            "allowed_tools",
            "allowed_providers",
            "allowed_model_families",
        ):
            _require_list_of_str(key, value)
        elif key == "max_tool_calls":
            if isinstance(value, bool) or not isinstance(value, int):
                raise PolicyError("rule 'max_tool_calls' must be an integer")
        # RUNTIME_DECLARED values are stored as-is; their runtime layer validates them.


def fingerprint_rules(rules: dict[str, Any]) -> str:
    """Content hash of a rules set, for dedup and for recording which policy a run enforced.

    Simple canonical JSON — policy rules are structured config, not prose, so the elaborate
    manifest canonicalisation is unnecessary here.
    """
    payload = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
