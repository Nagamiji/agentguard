# AgentGuard Q3 Execution Roadmap

**Planning only — no code. Stop after documentation; await founder approval.**
Translates the finalized council decisions (`../../.ai/decisions/` in ai-workbench)
into an execution order for this repo. Companion plans:
[`phase1-s7-production-readiness.md`](phase1-s7-production-readiness.md) ·
[`phase1-observability-plan.md`](phase1-observability-plan.md) ·
[`local-scan-engine-design.md`](local-scan-engine-design.md).

## Phase order
| Phase | What | Source decision |
|---|---|---|
| 1 · Security Foundation | Merge S7 · secret wiring + `enforce_admins` · **observability** minimum | 001 + audit #1 |
| 2 · Developer Experience | `agentguard scan --local` (advisory, availability-first) | 003 |
| 3 · Ecosystem Trust Layer | `validate-agent-card` / `validate-manifest` (MCP + A2A) | 002 |
| 4 · Trust Infrastructure | Ed25519 signing · provenance · verifiable verdicts · identity-first onboarding | 001/002/003 |

## Dependencies
```
S7 merge ─┬─> observability (min) ─┬─> scan --local (Stage A) ─> Ed25519 ─> authoritative local
          │                        └─> validate-manifest
          └─> (product fork: self-serve?) ─> identity-first onboarding (pre-GA)
```
- Observability gates trust in everything after it → **first**.
- `scan --local` **Stage A** needs only observability (audit-sync path); its
  **authoritative** form needs Phase 4 Ed25519.
- `validate-manifest` is independent of local-scan; both are post-observability.
- Identity-first onboarding (001) is gated on a **product decision** (self-serve or
  not), not on engineering.

## Risks
- **Solo-founder bandwidth** — five workstreams can't be concurrent; the order above
  is the throttle. Biggest risk is starting Phase 2/3 before observability.
- **In-memory metrics (obs G2)** don't survive multi-replica prod — resolve the
  scraping/recording-rule story before relying on the numbers.
- **S7 deploy gaps must land with the merge** — F1 (secret not in IaC) and F2 (XFF
  spoof) or prod onboarding is 503/ evadable.
- **Verify-before-build** on local scan: the CLI lives in the standalone package;
  don't size Phase 2 until its cloud-coupling is confirmed.

## Estimated complexity (rough, for sequencing — not commitments)
| Item | Size |
|---|---|
| S7 merge + F1 secret wiring + startup assertion | S |
| S7 F4/F2 (provisioning telemetry + trusted proxy) | S |
| Observability minimum (G3 gauge, G5 security events, G4 alert rules) | M |
| Observability G1 (OTel tracing) | M–L (deferred) |
| `scan --local` Stage A | M (reuses engine; ~3–5 d per council) |
| `validate-manifest` (MCP + A2A) | M (~3–5 d per Gemini) |
| Ed25519 signing (F3-adjacent, authoritative local) | M–L |

## Requires founder approval
- **F3 wildcard-key-default change** (`schemas.py:114-116`) — *breaking* for callers
  omitting role/scopes.
- **XFF trusted-proxy config** (F2) — a deployment/infra change.
- **OTel tracing** (obs G1) — new dependency + collector; in-scope or deferred?
- **Self-serve onboarding?** — the product fork that turns identity-first onboarding
  from backlog into a hard pre-GA blocker.
- Multi-replica metrics approach (obs G2).

## Do NOT build yet
- **A2A runtime / agent marketplace / agent council / execution layer** (002 —
  rejected). Build protocol-agnostic *validation*, nothing that runs agents.
- **Authoritative local verdicts** before Ed25519 (003 — advisory first).
- **Full IDP integration** before the self-serve product fork (001 — invitation
  tokens are the cheaper first step).
- **OTel** unless explicitly approved into Phase 1.

## One-task-per-iteration entry point
Recommended first task once approved: **merge S7 + F1 secret wiring + startup
assertion** — smallest, unblocks a clean `main`, and closes the highest-graded
finding. Everything else follows the dependency graph above. Each item is its own
branch → PR → human-approved merge; nothing auto-merges.
