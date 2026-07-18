"""Input fingerprints: a content hash over the *behaviour-relevant* parts of an agent.

This answers one question — "is this materially a different agent, or did someone fix a
typo in the description?" — and it is the trigger for re-running reliability evaluations.

The two failure modes are not symmetric:

* Too strict (fingerprint changes on cosmetic edits) -> we burn money re-running evals that
  were always going to pass.
* Too loose (fingerprint unchanged when behaviour changed) -> we certify an agent that now
  behaves differently. That is a reliability gate that lies, which is worse than no gate.

So the rule is: when in doubt, include the field. See docs/architecture/be-02-agent-registry.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# Bump when the canonicalisation rules below change. It is stored next to every hash: after
# a rules change every fingerprint changes, and without this we could not distinguish
# "the agent changed" from "we changed the hasher" — which would make every historical
# evaluation result uninterpretable.
FINGERPRINT_ALGO = "v1"

# Hashed. Everything not listed here is excluded by construction: a field nobody thought
# about cannot silently become part of an agent's identity.
BEHAVIOURAL_FIELDS: tuple[str, ...] = (
    "prompts",  # the behaviour itself
    "tools",  # names/descriptions/schemas are all model-visible
    "model",  # provider + PINNED snapshot id
    "params",  # temperature, top_p, max_tokens, seed, stop
    "retrieval",  # index, embedding model, top_k, filters
    "framework",  # orchestration semantics change between versions
)

# Recorded on the row, never hashed. None are model-visible; all churn for cosmetic reasons.
EXCLUDED_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "tags",
    "owner",
    "commit_message",
    "author",
    "created_at",
)

# Guards the recursive canonicaliser against a hostile or accidental deeply-nested manifest.
MAX_DEPTH = 32


class ManifestError(ValueError):
    """The manifest cannot be fingerprinted. Surfaces to the caller as a 400."""


def _normalise_text(text: str) -> str:
    """Strip cosmetic whitespace while preserving anything that could be semantic.

    Interior indentation is deliberately untouched: leading spaces inside a prompt template
    can carry meaning (Phoenix tracks template_format separately for exactly this reason).
    Only line endings, trailing whitespace and runs of blank lines are normalised.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]

    collapsed: list[str] = []
    for line in lines:
        if line == "" and collapsed and collapsed[-1] == "":
            continue  # collapse a run of blank lines to one
        collapsed.append(line)

    return "\n".join(collapsed).strip()


def _canonicalise(value: Any, depth: int = 0) -> Any:
    """Recursively put a value into a form where cosmetic differences cannot survive."""
    if depth > MAX_DEPTH:
        raise ManifestError(f"manifest nested deeper than {MAX_DEPTH} levels")

    if isinstance(value, dict):
        # Sorted keys: JSON object order is not behaviour. Absent and explicit-null must
        # produce the same hash, so None values are dropped rather than hashed as null.
        return {
            str(key): _canonicalise(value[key], depth + 1)
            for key in sorted(value, key=str)
            if value[key] is not None
        }

    if isinstance(value, list):
        return [_canonicalise(item, depth + 1) for item in value]

    if isinstance(value, str):
        return _normalise_text(value)

    if isinstance(value, bool | int | float) or value is None:
        return value

    raise ManifestError(f"manifest contains a non-JSON value of type {type(value).__name__}")


def _canonicalise_tools(tools: Any) -> Any:
    """Tools are a SET, not a sequence — reordering them does not change behaviour."""
    if not isinstance(tools, list):
        raise ManifestError("manifest 'tools' must be a list")

    canonical = [_canonicalise(tool) for tool in tools]

    # Sort by name where present, else by the tool's own canonical form, so the order is
    # stable regardless of how the caller happened to serialise it.
    def key(tool: Any) -> str:
        if isinstance(tool, dict):
            name = tool.get("name")
            if isinstance(name, str):
                return name
        return json.dumps(tool, sort_keys=True, separators=(",", ":"))

    return sorted(canonical, key=key)


def canonical_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Reduce a manifest to only what determines behaviour, in canonical form."""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a JSON object")

    canonical: dict[str, Any] = {}
    for field in BEHAVIOURAL_FIELDS:
        if field not in manifest or manifest[field] is None:
            continue
        if field == "tools":
            canonical[field] = _canonicalise_tools(manifest[field])
        else:
            canonical[field] = _canonicalise(manifest[field])

    if not canonical:
        raise ManifestError(
            "manifest contains none of the behavioural fields: " + ", ".join(BEHAVIOURAL_FIELDS)
        )

    return canonical


def compute_fingerprint(manifest: dict[str, Any]) -> str:
    """SHA-256 (hex) over the canonical, behaviour-only projection of a manifest."""
    canonical = canonical_manifest(manifest)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- secret detection -------------------------------------------------------------------
#
# A credential pasted into a manifest would be stored in a plaintext column AND hashed into
# a fingerprint that can never be redacted. Rejecting a legitimate write is recoverable;
# an unredactable secret is not. So this errs toward rejecting.

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    # (?!ant-) so an Anthropic key is not also reported as an OpenAI one — both start `sk-`.
    ("OpenAI API key", re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("AgentGuard API key", re.compile(r"\bag_[A-Za-z0-9_\-]{20,}")),
)


def find_secrets(manifest: dict[str, Any]) -> list[str]:
    """Return the names of credential types that appear anywhere in the manifest.

    Returns names only — never the matched text, which would copy the secret into logs and
    error bodies, i.e. exactly what this exists to prevent.
    """
    blob = json.dumps(manifest, ensure_ascii=False)
    return [label for label, pattern in _SECRET_PATTERNS if pattern.search(blob)]
