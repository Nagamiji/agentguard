"""Fingerprint canonicalisation properties.

These are the highest-value tests in BE-02. The fingerprint decides when reliability evals
re-run, so the two directions are asserted separately and explicitly:

* cosmetic change  -> fingerprint MUST NOT move (else we burn money re-running evals)
* behavioural change -> fingerprint MUST move (else we certify an agent that changed)

The second class is the one that matters: a gate that misses a real change is a gate that
lies. Each behavioural field gets its own test so a regression names the field it broke.
"""

import pytest

from keel.fingerprint import (
    BEHAVIOURAL_FIELDS,
    EXCLUDED_FIELDS,
    MAX_DEPTH,
    ManifestError,
    canonical_manifest,
    compute_fingerprint,
    find_secrets,
)


def _manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "prompts": [{"role": "system", "content": "You are a refund agent."}],
        "tools": [
            {
                "name": "issue_refund",
                "description": "Refund an order.",
                "schema": {"type": "object"},
            },
            {
                "name": "lookup_order",
                "description": "Find an order.",
                "schema": {"type": "object"},
            },
        ],
        "model": {"provider": "anthropic", "id": "claude-opus-4-8-20260115"},
        "params": {"temperature": 0.2, "max_tokens": 1024},
        "retrieval": {"index_id": "orders-v3", "embedding_model": "voyage-3", "top_k": 5},
        "framework": {"name": "langgraph", "version": "0.3.1"},
        "name": "Refund agent",
        "description": "Handles refunds.",
    }
    base.update(overrides)
    return base


# --- stability: cosmetic changes must not move the fingerprint ---------------------------


def test_fingerprint_is_deterministic() -> None:
    assert compute_fingerprint(_manifest()) == compute_fingerprint(_manifest())


def test_reordering_tools_does_not_change_fingerprint() -> None:
    a = _manifest()
    b = _manifest(tools=list(reversed(list(a["tools"]))))  # type: ignore[arg-type]
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_reordering_json_keys_does_not_change_fingerprint() -> None:
    a = _manifest(model={"provider": "anthropic", "id": "claude-opus-4-8-20260115"})
    b = _manifest(model={"id": "claude-opus-4-8-20260115", "provider": "anthropic"})
    assert compute_fingerprint(a) == compute_fingerprint(b)


@pytest.mark.parametrize(
    "prompt",
    [
        "You are a refund agent.   ",  # trailing spaces
        "You are a refund agent.\n",  # trailing newline
        "\nYou are a refund agent.\n\n",  # surrounding blank lines
        "You are a refund agent.\r\n",  # CRLF line endings
    ],
)
def test_cosmetic_whitespace_does_not_change_fingerprint(prompt: str) -> None:
    base = compute_fingerprint(_manifest())
    variant = _manifest(prompts=[{"role": "system", "content": prompt}])
    assert compute_fingerprint(variant) == base


def test_collapsing_blank_line_runs_does_not_change_fingerprint() -> None:
    a = _manifest(prompts=[{"role": "system", "content": "line one\n\nline two"}])
    b = _manifest(prompts=[{"role": "system", "content": "line one\n\n\n\nline two"}])
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_excluded_fields_do_not_change_fingerprint() -> None:
    base = compute_fingerprint(_manifest())
    for field in EXCLUDED_FIELDS:
        variant = _manifest(**{field: "something entirely different"})
        assert compute_fingerprint(variant) == base, f"{field} must not affect the fingerprint"


def test_absent_and_explicit_null_are_the_same() -> None:
    a = _manifest()
    b = _manifest()
    del b["retrieval"]
    c = _manifest(retrieval=None)
    assert compute_fingerprint(b) == compute_fingerprint(c)
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_unknown_fields_are_ignored() -> None:
    # A field nobody has considered must not silently become part of an agent's identity.
    assert compute_fingerprint(_manifest(some_future_field={"a": 1})) == compute_fingerprint(
        _manifest()
    )


# --- sensitivity: behavioural changes MUST move the fingerprint --------------------------


def test_interior_indentation_is_preserved() -> None:
    # Indentation inside a template can be semantic, so it is NOT normalised away.
    a = _manifest(prompts=[{"role": "system", "content": "a\n  indented"}])
    b = _manifest(prompts=[{"role": "system", "content": "a\nindented"}])
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_prompt_text_change_moves_fingerprint() -> None:
    variant = _manifest(prompts=[{"role": "system", "content": "You are a billing agent."}])
    assert compute_fingerprint(variant) != compute_fingerprint(_manifest())


def test_prompt_order_change_moves_fingerprint() -> None:
    # Prompts are a sequence, unlike tools: order is behaviour.
    a = _manifest(
        prompts=[{"role": "system", "content": "first"}, {"role": "user", "content": "second"}]
    )
    b = _manifest(
        prompts=[{"role": "user", "content": "second"}, {"role": "system", "content": "first"}]
    )
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_adding_a_tool_moves_fingerprint() -> None:
    tools = list(_manifest()["tools"])  # type: ignore[arg-type]
    tools.append({"name": "cancel_order", "description": "Cancel.", "schema": {}})
    assert compute_fingerprint(_manifest(tools=tools)) != compute_fingerprint(_manifest())


def test_tool_description_change_moves_fingerprint() -> None:
    # A tool's description IS model-visible, unlike the agent's own description. These two
    # fields are both called "description"; treating them the same breaks the gate.
    tools = [
        {
            "name": "issue_refund",
            "description": "Refund an order, up to $10000.",
            "schema": {"type": "object"},
        },
        {
            "name": "lookup_order",
            "description": "Find an order.",
            "schema": {"type": "object"},
        },
    ]
    assert compute_fingerprint(_manifest(tools=tools)) != compute_fingerprint(_manifest())


def test_tool_schema_change_moves_fingerprint() -> None:
    tools = [
        {"name": "issue_refund", "description": "Refund an order.", "schema": {"type": "string"}},
        {"name": "lookup_order", "description": "Find an order.", "schema": {"type": "object"}},
    ]
    assert compute_fingerprint(_manifest(tools=tools)) != compute_fingerprint(_manifest())


def test_model_snapshot_change_moves_fingerprint() -> None:
    # The whole reason we hash a PINNED snapshot rather than a floating alias.
    variant = _manifest(model={"provider": "anthropic", "id": "claude-opus-4-8-20260301"})
    assert compute_fingerprint(variant) != compute_fingerprint(_manifest())


def test_param_change_moves_fingerprint() -> None:
    variant = _manifest(params={"temperature": 0.9, "max_tokens": 1024})
    assert compute_fingerprint(variant) != compute_fingerprint(_manifest())


def test_retrieval_change_moves_fingerprint() -> None:
    variant = _manifest(
        retrieval={"index_id": "orders-v4", "embedding_model": "voyage-3", "top_k": 5}
    )
    assert compute_fingerprint(variant) != compute_fingerprint(_manifest())


def test_framework_version_change_moves_fingerprint() -> None:
    # Decision (proposal §9.1): framework version is behaviour — 0.2->0.3 can change
    # orchestration semantics.
    variant = _manifest(framework={"name": "langgraph", "version": "0.2.7"})
    assert compute_fingerprint(variant) != compute_fingerprint(_manifest())


@pytest.mark.parametrize("field", BEHAVIOURAL_FIELDS)
def test_dropping_any_behavioural_field_moves_fingerprint(field: str) -> None:
    variant = _manifest()
    del variant[field]
    assert compute_fingerprint(variant) != compute_fingerprint(_manifest())


# --- shape ------------------------------------------------------------------------------


def test_fingerprint_is_sha256_hex() -> None:
    fp = compute_fingerprint(_manifest())
    assert len(fp) == 64
    assert set(fp) <= set("0123456789abcdef")


def test_canonical_manifest_keeps_only_behavioural_fields() -> None:
    canonical = canonical_manifest(_manifest())
    assert set(canonical) == set(BEHAVIOURAL_FIELDS)


def test_empty_manifest_is_rejected() -> None:
    with pytest.raises(ManifestError, match="behavioural fields"):
        compute_fingerprint({"name": "cosmetic only"})


def test_non_object_manifest_is_rejected() -> None:
    with pytest.raises(ManifestError, match="JSON object"):
        compute_fingerprint(["not", "an", "object"])  # type: ignore[arg-type]


def test_deeply_nested_manifest_is_rejected() -> None:
    nested: dict[str, object] = {"depth": 0}
    for _ in range(MAX_DEPTH + 5):
        nested = {"nest": nested}
    with pytest.raises(ManifestError, match="nested deeper"):
        compute_fingerprint(_manifest(params=nested))


def test_non_json_value_is_rejected() -> None:
    with pytest.raises(ManifestError, match="non-JSON value"):
        compute_fingerprint(_manifest(params={"callback": {1, 2}}))


# --- secret detection -------------------------------------------------------------------


# Every value below is fabricated — the `gitleaks:allow` markers say so to our own secret
# scanner, which cannot tell a fake key from a real one and is right to flag both. The AWS
# entry is the example key from their own documentation.
@pytest.mark.parametrize(
    ("label", "secret"),
    [
        ("Anthropic API key", "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA"),  # gitleaks:allow
        ("OpenAI API key", "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"),  # gitleaks:allow
        ("AWS access key id", "AKIAIOSFODNN7EXAMPLE"),  # gitleaks:allow
        ("GitHub token", "ghp_" + "A" * 36),  # gitleaks:allow
        ("Google API key", "AIza" + "A" * 35),  # gitleaks:allow
        ("Slack token", "xoxb-123456789012-abcdefghijkl"),  # gitleaks:allow
        ("AgentGuard API key", "ag_" + "A" * 25),  # gitleaks:allow
    ],
)
def test_secrets_are_detected(label: str, secret: str) -> None:
    manifest = _manifest(prompts=[{"role": "system", "content": f"Use the key {secret}"}])
    assert label in find_secrets(manifest)


def test_private_key_block_is_detected() -> None:
    manifest = _manifest(
        prompts=[{"role": "system", "content": "-----BEGIN RSA PRIVATE KEY-----\nabc"}]
    )
    assert "private key block" in find_secrets(manifest)


def test_secret_is_found_in_excluded_fields_too() -> None:
    # The description is not hashed, but it is still stored in plaintext.
    assert find_secrets(_manifest(description="key: sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA"))


def test_clean_manifest_has_no_secrets() -> None:
    assert find_secrets(_manifest()) == []


def test_find_secrets_never_returns_the_secret_itself() -> None:
    # Returning the match would copy the credential into logs and error bodies — the exact
    # thing this check exists to prevent.
    secret = "sk-ant-api03-BBBBBBBBBBBBBBBBBBBBBB"  # noqa: S105 — a fake key, that is the point
    found = find_secrets(_manifest(prompts=[{"role": "system", "content": secret}]))
    assert found == ["Anthropic API key"]
    assert all(secret not in item for item in found)
