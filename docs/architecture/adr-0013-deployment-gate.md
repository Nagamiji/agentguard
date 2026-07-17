# ADR 0013 — The deployment gate (CLI + GitHub Action)

**Status:** accepted · **Date:** 2026-07-17 · **Task:** Phase 5 · **Builds on:** ADR 0008–0012

## Architecture review (before building)

The server already answers the question a CI check needs: `GET /agents/{id}/gate` and
`/risk` return a decision + findings for a fingerprint, and the policy engine feeds them.
So Phase 5 is **not** more platform — it is the **client + CI surface** over what exists. That
scoping decision drove everything: no new tables, no migration, one additive response field.

## Decision

Ship a CLI and a composite GitHub Action. A developer's CI runs `agentguard scan`; its **exit
code is the product contract** — non-zero fails the job and blocks the merge.

### 1. Pull model, not push

The CLI calls the API (over TLS + API key). We deliberately did **not** build inbound GitHub
webhooks this cycle: the pull model needs no public callback endpoint, no webhook-signature
verification, and no per-customer GitHub App. Webhooks are a real feature for a later "push"
mode; they are not needed for the wedge and would have tripled the surface.

### 2. The exit code is the contract

```
0   allowed            20  blocked (deploy must not proceed)
10  error (fail closed)  30  unknown / never evaluated (fail closed)
```

`--fail-on` tunes which verdicts are non-zero; the default (`unknown`) blocks on **blocked +
unknown**, because a gate that exits 0 when it could not tell is not a gate. Every failure
path — network error, HTTP error, unparseable response — maps to a non-zero code. This is the
same fail-closed posture as the server gate, now enforced client-side too.

### 3. SARIF, so findings land in the PR

`scan` emits SARIF 2.1.0; the Action uploads it with `github/codeql-action/upload-sarif`, so
each finding (a failed check or a static policy violation) shows up in GitHub's Security tab
and inline on the PR. Severity maps to SARIF level (critical/high → error). The Action uploads
SARIF **even when the gate fails the job** (`if: always()`), so the developer sees *why* it
was blocked, not just that it was.

### 4. Signed verdicts — honestly scoped

`GET /gate` includes an **HMAC** signature over `(fingerprint, decision, run_id)` when
`KEEL_SIGNING_SECRET` is set. It proves a verdict was produced by a holder of the secret and
not altered — integrity for a party that trusts this server and holds the key. It is **not**
third-party non-repudiation (anyone with the key can forge). That needs asymmetric signing
(an Ed25519 keypair, public key published) — the documented upgrade. Signing over `run_id`
rather than a timestamp avoids a serialization-format mismatch between signer and verifier.

### 5. Reuse over rebuild

The CLI talks to the existing endpoints; the only server change is the additive
`GateOut.signature`. No migration. The CLI's HTTP layer is a Protocol so the same flow runs
in-process against a `TestClient` — which is how the "fake GitHub workflow" test drives the
whole thing without a network.

## Validated

- **Fake workflow (in-process):** a blocked deployment exits 20 with an error-level SARIF
  result; a safe one exits 0 with no results; a disallowed provider blocks via `policy check`
  with no run; a verdict signs and is tamper-evident.
- **Real subprocess over HTTP:** `agentguard scan` against a live uvicorn returned exit 20,
  printed the verdict, and wrote valid SARIF 2.1.0.
- **Production image:** the `agentguard` entry point is installed in the Docker image.

## Consequences

- **Good:** the platform becomes a control a developer *feels* — a red CI check. Fail-closed
  end to end. No new persistence, so low risk. Provider-agnostic runner (`--runner vertex`
  for real model evaluation in the customer's own environment).
- **Costs / deferred, honestly:**
  - **No webhooks / push mode** — pull only this cycle.
  - **No deployment-record table / CI-run tracking table** — the immutable `eval_runs` already
    record every evaluation; a dedicated deployment-audit table is additive future work.
  - **Signing is symmetric** — integrity, not third-party attestation (asymmetric is the upgrade).
  - **No async** — `scan` is synchronous; fine while runs are seconds. A long real-model scan
    over many scenarios may want a job model later.
  - The Action's CLI install assumes a package index (`install-command` is overridable) — the
    CLI is not yet published to PyPI.
