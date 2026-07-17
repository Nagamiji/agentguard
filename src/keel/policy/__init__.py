"""The policy engine: what an org, project or agent is *allowed* to do, resolved by
precedence and compiled into checks the evaluation engine enforces.

Design: ADR 0012. The eval engine consumes COMPILED policy — it never hardcodes a limit.
A refund ceiling lives in a policy once; the compiler turns it into a check that every scan
applies. Change the policy, and every agent under it is re-gated on the next run.
"""

from keel.policy.compiler import CompiledPolicy, compile_policy
from keel.policy.resolver import ResolvedRule, resolve
from keel.policy.rules import PolicyError, fingerprint_rules, validate_rules

__all__ = [
    "CompiledPolicy",
    "PolicyError",
    "ResolvedRule",
    "compile_policy",
    "fingerprint_rules",
    "resolve",
    "validate_rules",
]
