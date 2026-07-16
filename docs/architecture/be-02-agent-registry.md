# BE-02 — Agent Registry: architecture proposal

**Status:** **approved 2026-07-16** — §9 decisions settled, implementation in progress.
**Date:** 2026-07-16
**Prime-directive fit:** the registry is what a developer *connects*, and the fingerprint is
what decides *when to re-run reliability tests*. Both are on the critical path of
`connect an agent → run reliability tests in CI → get a failure report → block the deploy`.

---

## 1. Summary

Three tables, following the shape every mature registry independently converged on:

| Concept | Mutability | Purpose |
|---|---|---|
| `agents` | mutable | Stable identity. Rename freely; references never break. |
| `agent_versions` | **immutable** | Frozen config snapshot. Never updated after insert. |
| `agent_aliases` | mutable | Named pointer (`production`, `champion`) → one version. |

Identity of a version is a **canonicalized content hash** (the "input fingerprint"), plus a
human-facing monotonic `sequence_number` for display and ordering.

---

## 2. Prior art (what we're copying, and what we're refusing to copy)

Researched: MLflow Model Registry, W&B Registry, LangSmith Prompt Hub, Langfuse, Arize
Phoenix, Braintrust, PromptLayer, Humanloop, TruLens, OpenAI Evals, Ragas.

**Copy — the three-tier split.** MLflow, W&B, Langfuse, Phoenix, PromptLayer and Humanloop
all arrived independently at *stable identity → immutable version → mutable pointer*. That
convergence is the strongest signal in the research. It is also cheap to build; there is no
"buy" that avoids it, because for most of those vendors this shape **is** the product.

**Refuse — MLflow's `stage` enum.** MLflow shipped a fixed
`None→Staging→Production→Archived` stage per version and
[deprecated it](https://github.com/mlflow/mlflow/issues/10336) after "extensive feedback on
the inflexibility": one field was carrying lifecycle status, deployment environment, *and*
access control. They split it into tags + aliases + auth. We start there instead of
learning it twice — hence `agents.status` (record lifecycle only) and `agent_aliases`
(deployment pointer) as separate concepts from day one.

**The fingerprint is the piece nobody has shipped.** TruLens is closest — its `app_id` is
"by default a hash of app content as json" — but it hashes raw JSON without canonicalizing,
so cosmetic edits still produce a new identity. Langfuse users
[asked for exactly this](https://github.com/orgs/langfuse/discussions/2161) ("only create a
version when content differs") and were told it's "somewhat niche," not on the roadmap. W&B
has real content-addressed dedup, but at file-digest level, not over behavior-relevant
config. **This is legitimate IP and it maps directly to our prime directive**: re-run evals
only when behavior may have changed.

---

## 3. The fingerprint — the one decision that matters

The fingerprint answers: *"is this materially a different agent, or did someone fix a typo
in the description?"* Wrong in one direction we burn money and CI time re-running evals on
whitespace. Wrong in the other we **certify an agent whose behavior actually changed** —
which is a reliability gate that lies. That second failure is the one that ends the company,
so the rule is: **when in doubt, include the field.** A spurious re-run costs dollars; a
missed re-run costs the product's premise.

### In scope (canonicalized, then hashed)

| Field | Why |
|---|---|
| `prompts` (system/user templates, in order) | The behavior. |
| `tools` (name, description, JSON schema) | Adding/removing a tool changes what it can do. Descriptions/schemas are model-visible, so they are behavior. |
| `model` (provider + **pinned snapshot id**) | Humanloop treated `model` as a top-level version trigger. Hash `claude-opus-4-6-20260115`, never bare `claude-opus-4-6` — an unpinned alias silently changes behavior underneath us. |
| `params` (temperature, top_p, max_tokens, seed, stop) | Decoding params change behavior. |
| `retrieval` (index id, embedding model, top_k, filters) | Same agent + different corpus = different agent. |
| `framework` + major version | LangGraph 0.2 → 0.3 can change orchestration semantics. |

### Explicitly excluded (recorded on the row, outside the hash)

`name`, `description`, `tags`, `owner`, `commit message`, `created_at`, `author`.
None are model-visible. All change constantly for cosmetic reasons.

> ⚠️ **The trap:** a tool's `description` **is** model-visible and therefore in-scope, while
> the *agent's* `description` is not. They are both called "description". Getting this
> backwards silently breaks the gate.

### Canonicalization (this is what nobody else does)

Before hashing:
1. **Sort** tools by name; sort JSON object keys recursively. Order is not behavior.
2. **Normalize** prompt whitespace: strip trailing whitespace per line, collapse >1 blank
   line, normalize line endings. Do **not** touch interior spacing — indentation inside a
   template can be semantic (Phoenix tracks `template_format` separately for this reason).
3. **Drop** null/absent optional fields rather than hashing `null` — absent and explicit-null
   must not produce different fingerprints.
4. Serialize canonical JSON (sorted keys, no whitespace, UTF-8), hash **SHA-256**, store hex.
5. **Version the algorithm**: store `fingerprint_algo = "v1"` alongside. When canonicalization
   rules change, every hash changes; without a recorded algo version we cannot tell "behavior
   changed" from "we changed the hasher" — and every historical eval result becomes
   uninterpretable.

Canonicalization is pure, so it gets property-based tests: reordering tools, reformatting
whitespace, and re-serializing must **not** change the hash; changing any in-scope value
**must**.

### Dedup

`POST /agents/{id}/versions` with an existing fingerprint returns the existing version
(`200`), not a new one (`201`). This is Langfuse's documented gap, fixed at the source.

---

## 4. Schema

All three tables carry `organization_id` and their own RLS policy. **RLS does not inherit
through foreign keys** — a child table without its own policy is a cross-tenant leak, even
when its parent is protected.

```
agents                          agent_versions                    agent_aliases
──────                          ──────────────                    ─────────────
id            uuid pk           id                uuid pk         id              uuid pk
organization_id uuid fk ──┐     organization_id   uuid fk ──┐     organization_id uuid fk ──┐
name          varchar(200)│     agent_id          uuid fk ───┼──> id              │
slug          varchar(200)│     sequence_number   int         │    agent_id        uuid fk ──┘
description   text        │     fingerprint       char(64)    │    name            varchar(100)
framework     varchar(50) │     fingerprint_algo  varchar(10) │    version_id      uuid fk
status        varchar(20) │     manifest          jsonb        │    created_at      timestamptz
metadata      jsonb       │     created_at        timestamptz  │    updated_at      timestamptz
created_at    timestamptz │                                    │
updated_at    timestamptz │                                    │
                          └──> organizations.id <──────────────┘
```

Constraints:
- `agents`: `UNIQUE (organization_id, slug)` — slug is the stable handle across renames.
- `agent_versions`: `UNIQUE (agent_id, fingerprint)` — enforces dedup **in the database**,
  not just in the handler. Also `UNIQUE (agent_id, sequence_number)`.
- `agent_aliases`: `UNIQUE (agent_id, name)` — one `production` per agent.
- `status`: `CHECK (status IN ('active','archived'))` — lifecycle of the *record* only.
  Never deployment state. (See MLflow above.)

`manifest` is `jsonb`, frozen at insert. No `UPDATE` endpoint exists for versions.

---

## 5. Two defects in BE-01 this must fix first

Both found while auditing; both verified against a real Postgres, not inferred.

### 5.1 `GRANT ON ALL TABLES` is a snapshot — BE-02 breaks without this

`0001_init.py` grants DML `ON ALL TABLES IN SCHEMA public` to `keel_app`. That is evaluated
**once, at execution time**. Proven locally: a table created after that migration gives
`ERROR: permission denied for table ...` to `keel_app`, while `projects` works.

So `agents` would 500 on the first request — **at runtime, not in CI**, because CI runs
migrations and tests in one pass where the ordering hides it.

The obvious fix — repeat the `GRANT` block in `0002` — works but is a landmine: every future
migration must remember, and forgetting once ships a table that works in tests and fails in
production. The durable fix, verified locally:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE keel IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO keel_app;
```

Confirmed: after this, a newly created table is readable by `keel_app` with no explicit
grant. Migrations run as `keel` (the table owner), so the role scoping is correct. `0002`
applies this **and** the explicit grant for its own tables (default privileges do not apply
retroactively).

### 5.2 A stale comment that teaches the wrong lesson

`0001_init.py:60` says `FORCE ROW LEVEL SECURITY` is needed because "our app connects as the
owner". It does not — it connects as `keel_app`, which is neither owner nor superuser
(`config.py:15`). `FORCE` is still correct defense-in-depth, but the stated reason is wrong,
and a future engineer reasoning from it could conclude the app role is privileged and "fix"
something dangerous. Correct the comment, keep the `FORCE`.

Also: `middleware.py:21` sets `request.state.org_id` from a **client-controlled `X-Org-ID`
header**. It authorizes nothing today (`require_org` is the real path), but it is a
tenant-shaped value sitting in request state next to a registry that must never trust one.
Delete it.

---

## 6. API

All under `/v1`, all requiring `CurrentOrg`, all RLS-scoped. Cross-tenant access returns
**404, not 403** — matching `test_isolation.py:82`; 403 would confirm the row exists.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/agents` | 201. `slug` auto-derived from name if absent. |
| `GET` | `/agents` | List. **No `.where(organization_id)`** — RLS scopes it; that absence is the isolation test. |
| `GET` | `/agents/{id}` | 404 if not this tenant's. |
| `PATCH` | `/agents/{id}` | name/description/status/metadata only. Never version data. |
| `POST` | `/agents/{id}/versions` | Computes fingerprint. **201** new, **200** if fingerprint exists (dedup). |
| `GET` | `/agents/{id}/versions` | Ordered by `sequence_number`. |
| `GET` | `/agents/{id}/versions/{fingerprint}` | Resolve by content hash. |
| `PUT` | `/agents/{id}/aliases/{name}` | Point alias at a version. |
| `GET` | `/agents/{id}/aliases/{name}` | Resolve to a **concrete** version. |

No `PUT`/`PATCH`/`DELETE` on versions. Immutability is structural.

---

## 7. Threat model

| Threat | Control |
|---|---|
| Cross-tenant read of another org's agents | RLS policy on all 3 tables + a mirror test per table in `test_isolation.py`. |
| Child table leaks via FK | Every table has its own `organization_id` + policy. Tested per table. |
| **Alias repointed to another tenant's version** | FK alone won't catch it — RLS makes the row invisible, so the insert fails, but we assert it explicitly with a test. |
| Manifest treated as inert data | [LangSmith CVE GHSA-3644-q5cj-c5c7](https://github.com/langchain-ai/langsmith-sdk/security/advisories/GHSA-3644-q5cj-c5c7): pulling prompts deserialized untrusted manifests, letting attackers redirect model traffic and exfiltrate env vars via `secrets_from_env`. **We store manifests as inert `jsonb` and never deserialize into executable objects.** Their postmortem: "prompts should be treated as executable configuration rather than plain text." |
| **Secrets pasted into a manifest** | An API key in a prompt would be stored plaintext and, worse, **hashed into a fingerprint that cannot be redacted after the fact**. Size-cap the manifest and reject obvious credential patterns at write time. Needs a decision — see §9. |
| Pinned version silently floats to latest | [MLflow #8078](https://github.com/mlflow/mlflow/issues/8078): `load_model(version=4)` returned latest anyway. Alias resolution always logs the concrete fingerprint used. |
| Fingerprint collision | SHA-256. Not a practical concern. |
| Manifest as a DoS vector | Cap size (proposed 256 KB); reject deeper than N levels before canonicalizing (recursive sort on hostile input). |

---

## 8. Implementation plan

Migration `0002` must repeat the guarded GRANT for its own tables **and** add default
privileges for future ones.

1. `migrations/versions/0002_agent_registry.py` — 3 tables, RLS per table, GRANT + default privileges, correct the stale comment.
2. `src/keel/fingerprint.py` — canonicalize + hash. Pure, no I/O. **Written first, with property tests.**
3. `src/keel/models.py` — `Agent`, `AgentVersion`, `AgentAlias` (BE-01 style: no `relationship()`, uuid4 defaults, `_utcnow`).
4. `src/keel/schemas.py` — `AgentCreate/Out`, `AgentVersionCreate/Out`, `AliasOut`.
5. `src/keel/api/agents.py` — router, sync handlers, `CurrentOrg` + `DbSession`.
6. `src/keel/main.py` — include router.
7. `tests/test_fingerprint.py` — canonicalization properties (the highest-value tests here).
8. `tests/test_isolation.py` — mirror isolation tests for all 3 tables + cross-tenant alias.
9. Delete the `X-Org-ID` scaffold.

Sequenced so §5.1 lands first: without it every later step fails at runtime.

---

## 9. Decisions — settled 2026-07-16

1. **`framework` + version is IN the fingerprint.** A LangGraph 0.2→0.3 bump can change
   orchestration semantics, so it is behavior. Accepted cost: framework bumps trigger
   eval re-runs that may turn out to be no-ops. Consistent with "when in doubt, include" —
   a spurious re-run costs dollars; a missed one certifies an agent whose behavior changed.
2. **Reject suspected secrets at write time** (`400`, clear error). False positives block a
   legitimate write, which is recoverable; the alternative writes a credential into a
   plaintext column *and* into a one-way hash that can never be redacted. Manifest bodies
   are never logged.
3. **`sequence_number` is per agent** (1, 2, 3… within each agent) — matches Langfuse and
   Phoenix, reads naturally ("agent X v3"), and does not leak how many agents an org has.

---

## 10. Explicitly out of scope

Deployment gating logic (`EVAL-01`), eval execution, the dashboard, and SDK ingestion. This
task delivers the registry and the fingerprint only — the substrate those depend on.
