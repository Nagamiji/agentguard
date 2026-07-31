"""The Proof Object — AgentGuard's actual product.

A verdict alone ("BLOCKED") is an opinion. A Proof Object is a *self-attested evidence
record*: for every scenario it states what was tested, what was expected, what was
observed, why the decision was made, and what the limitations are. A security engineer
can read it and answer "why should I believe this?" without trusting our summary.

Honesty rules baked into the types (do not relax without a design decision):

  * ``self_attested = True`` / ``cryptographically_verified = False`` — in V1 the observed
    behaviour and ``tools_executed: 0`` are recorded by AgentGuard's own runner. That is
    testimony, not cryptographic proof. Signing (Cosign/Sigstore/in-toto) is a later phase
    that flips ``cryptographically_verified`` to True — the field exists now so consumers
    can branch on it and never mistake V1 evidence for a signed attestation.

  * ``execution_mode`` is carried on every object and baked into SARIF rule ids, so a
    STATIC CHECK finding can never be confused with a BEHAVIOR SIMULATION finding even if
    the surrounding CLI framing is stripped (a copied log line, GitHub's Security tab).

  * ``result`` distinguishes ``skipped`` from ``pass``. A scenario that could not run
    (e.g. a behavioural test in static mode) is never reported as passing.

  * ``evidence_digest`` covers *outcomes*, not just inputs. It is a reproducibility /
    content digest ("is this the same evidence?"), NOT a tamper seal — it is unsigned, so
    whoever edits the report can recompute it. Never describe it as proof of authenticity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ExecutionMode = Literal["static", "live"]
Result = Literal["pass", "fail", "skipped"]


@dataclass
class ProofObject:
    """Evidence for exactly one scenario. One question answered per field."""

    scenario_id: str
    name: str
    # Taxonomy — TAGS, never a coverage metric. "unknown" is allowed; never force a mapping.
    asi_id: str  # e.g. "ASI02" or "unknown"
    asi_name: str
    llm_id: str
    attack_category: str  # How was it tested?
    attack_input: str  # What was sent?
    expected_behavior: str  # What should a safe agent do?
    observed_behavior: dict[str, Any]  # What actually happened? {text, tool_calls}
    result: Result  # pass | fail | skipped
    execution_mode: ExecutionMode  # static | live — undroppable
    confidence: str
    limitations: str
    policy_check: dict[str, Any] | None = None  # {check_type, expected, observed, passed}
    calculation: str | None = None  # visible math, e.g. "5000 > 100 -> violated"
    skip_reason: str | None = None
    tools_executed: int = 0  # REAL tools run — always 0 by design
    self_attested: bool = True
    cryptographically_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructuralCheck:
    """A deterministic, no-model check that static mode CAN honestly evaluate."""

    check_id: str
    description: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Coverage:
    """What was tested and — just as loudly — what was not.

    Denominator is the scenario library, never the ASI taxonomy: one trivial scenario per
    ASI category would let someone claim "100% ASI coverage", so ASI ids are tags only.
    """

    execution_mode: ExecutionMode
    scenarios_total: int
    passed: int
    failed: int
    skipped: int
    asi_tags: list[str] = field(default_factory=list)  # tags present, NOT a percentage
    untested_surfaces: list[str] = field(default_factory=list)
    structural_checks_evaluated: int = 0

    @property
    def evaluated(self) -> int:
        return self.passed + self.failed

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scenarios_evaluated"] = self.evaluated
        return data


# Surfaces AgentGuard does not test — stated so coverage cannot be read as "complete".
DEFAULT_UNTESTED_SURFACES: tuple[str, ...] = (
    "multi-agent delegation",
    "runtime tool execution and tool-response injection",
    "external database / API permissions",
    "human-approval workflows",
    "long-term memory poisoning across sessions",
)


def compute_evidence_digest(
    *,
    agent_fingerprint: str,
    scenario_lib_version: str,
    execution_mode: ExecutionMode,
    fingerprint_algo: str,
    proof_objects: list[ProofObject],
    redaction_policy: str | None = None,
) -> str:
    """A content/reproducibility digest over inputs AND outcomes.

    Same agent + same scenario library + same mode + same recorded outcomes => same digest.
    This is deliberately NOT a tamper seal (it is unsigned; an editor can recompute it).
    It answers "is this the same evidence?", not "has this been tampered with?".

    The proof objects passed here are already redacted, so the digest covers the artifact a
    reader actually holds and stays recomputable from it. `redaction_policy` names the rules
    that produced them (None when redaction was disabled); without it, two runs scrubbed by
    different pattern sets could collide and read as identical evidence.
    """
    outcomes = [
        {
            "id": p.scenario_id,
            "result": p.result,
            "observed": p.observed_behavior,
            "policy_passed": (p.policy_check or {}).get("passed"),
        }
        for p in proof_objects
    ]
    payload = json.dumps(
        {
            "agent_fingerprint": agent_fingerprint,
            "scenario_lib_version": scenario_lib_version,
            "execution_mode": execution_mode,
            "fingerprint_algo": fingerprint_algo,
            "redaction_policy": redaction_policy,
            "outcomes": outcomes,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
