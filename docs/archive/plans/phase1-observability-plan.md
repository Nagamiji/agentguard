# Phase 1 · Observability Plan

**Planning only — no code.** Observability is the production-readiness audit's #1
gap and the dependency for trusting everything else. This plan **starts from what
already exists** (more than expected) and closes the real holes.

## Current state (audited)
| Signal | State | Evidence |
|---|---|---|
| Structured JSON logs | ✅ present | `logging.py` — `JsonFormatter` |
| Context propagation (request_id/org_id/run_id) | ✅ present | `logging.py:49-61` via contextvars |
| In-process Prometheus metrics + `/metrics` | ✅ present | `metrics.py`; endpoint `api/health.py:41-44` |
| HTTP req count + latency | ✅ wired | `middleware.py:45,52` |
| Eval runs / scenarios / policy violations / scan totals+failures / usage-limit hits | ✅ wired | `api/evals.py:224-369`, `api/agents.py:75` |
| Audit trail | ✅ present | `audit.py` `record_audit_event`, `api/audit.py` |

**Takeaway: this is "wire and scale what exists," not "build from zero."**

## Gaps (audited)
- **G1 · No distributed tracing.** No OpenTelemetry anywhere in `src/keel` despite
  the stack doc naming OTel. No cross-service/DB span timing.
- **G2 · Metrics are in-process / in-memory.** `metrics.py` holds counters in a
  process-local dict. They **reset on restart** and **do not aggregate across
  replicas** — each pod reports its own numbers. Multi-replica prod needs
  per-instance scraping + recording rules, or a shared aggregation store.
- **G3 · Dangling gauge.** `agentguard_active_organizations` is defined but **never
  `set()`** (grep: no caller) — it will always read 0.
- **G4 · No alerting.** No Alertmanager rules / notification path in the repo.
- **G5 · No security-event telemetry.** The S7 provisioning guard emits nothing on
  403/429/503 (`provisioning.py`) — abuse is invisible. (Shared with S7 plan F4.)

## Minimum observability layer (design)
Scoped to close G2–G5 cheaply; G1 (OTel) is deferred as a larger, separate effort.

**Metrics** (mostly present — additions marked ➕):
- scans executed — `agentguard_scan_total{decision,environment}` ✅
- pass/block ratio — derive from `agentguard_scan_total` + `_failures_total` ✅
- failure categories — `policy_violations_total{rule_type}`, `scenarios_failed_total{category}` ✅
- latency — `http_request_duration_seconds`, `eval_run_duration_seconds` ✅
- API availability / error rate — derive from `http_requests_total{status}` ✅
- ➕ set `active_organizations` (fix G3) — update on org create/deactivate or a periodic query
- ➕ `provisioning_events_total{result}` (403/429/503/ok) — fixes G5, feeds abuse alerts
- ➕ worker/eval error rate — a counter on `RunStatus.ERRORED` paths (`engine.py:112-115`)

**Logs** (foundation present):
- structured security events ➕ (auth failures, provisioning rejections) — G5
- audit trail ✅ (`audit.py`)
- tenant isolation ✅ (`org_id` in every log via context)

**Alerts** (new — G4; define as Prometheus/Alertmanager rules, infra not app code):
- API downtime / high 5xx rate (from `http_requests_total`)
- failed workers / eval error-rate spike
- abnormal block-rate spike (`agentguard_scan_failures_total`)
- provisioning abuse (429/503 spike on `provisioning_events_total`)

**Tracing (G1):** OTel spans around request → policy resolve → eval → DB. **Deferred**
— it's the largest item and not required for the minimum. Recommend a separate
decision (adds a dependency + collector infra).

## Decision needed from founder
- **G2 fix approach:** accept per-instance scraping + Prometheus recording rules
  (cheap, standard) vs. a shared aggregation store (more infra). Recommend the
  former for now.
- **G1 (OTel):** in Phase 1 minimum, or deferred? Recommend **deferred**.

## Suggested Phase-1 order (cheapest, highest-signal first)
1. ➕ Fix G3 (set `active_organizations`) + G5 (provisioning + auth security events).
   Small, and G5 also closes S7 F4.
2. Define alert rules (G4) on the metrics that already exist.
3. Decide + document the G2 multi-replica story (recording rules).
4. (Separate decision) G1 OTel tracing.
