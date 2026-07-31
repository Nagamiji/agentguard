# Beta Release Checklist

This checklist must be completed before opening the controlled public beta to external customers.

---

## Security

- [ ] API keys stored as SHA-256 hashes only — no plaintext in DB
- [ ] RLS policies verified on all tenant tables:
  - [ ] `agents`
  - [ ] `agent_versions`
  - [ ] `agent_aliases`
  - [ ] `eval_runs`
  - [ ] `eval_results`
  - [ ] `api_keys`
  - [ ] `usage_events`
- [ ] Authentication tested:
  - [ ] Missing auth → 401
  - [ ] Invalid key → 401
  - [ ] Revoked key → 401
  - [ ] Suspended org → 403
  - [ ] Wrong scope → 403
- [ ] No secrets in logs — verified by manual scan of sample log output
- [ ] No secrets in git history — gitleaks full-scan passed
- [ ] Production startup fails safely when secrets are missing (verified in staging)
- [ ] Dependency CVE scan: `pip-audit` reports zero HIGH/CRITICAL
- [ ] Container CVE scan: Trivy reports zero actionable HIGH/CRITICAL

---

## Infrastructure

- [ ] PostgreSQL backups configured and tested restore verified
- [ ] Redis persistence enabled (AOF or RDB snapshots)
- [ ] Monitoring enabled:
  - [ ] `/metrics` Prometheus endpoint accessible to scraper
  - [ ] Alerting on `agentguard_scan_failures_total` spike
  - [ ] Alerting on DB connectivity failures (`readyz.checks.database = false`)
- [ ] Logs shipped to log aggregation (Datadog / CloudWatch / Loki)
- [ ] Cloudflare Worker deployed and verified
- [ ] Load balancer health checks pointing to `/healthz` (liveness) and `/readyz` (readiness)

---

## Product

- [ ] Onboarding works end-to-end:
  - [ ] `POST /v1/onboarding` creates org + key
  - [ ] Key works immediately after creation
  - [ ] Agent can be registered
  - [ ] Scan can be executed
  - [ ] Gate decision returned
- [ ] Billing events recorded: `scan_executed` appears in `usage_events` after each scan
- [ ] Plan limits enforced:
  - [ ] Free: >1 agent registration blocked with 402
  - [ ] Free: >10 scans blocked with 402
- [ ] Demo environment tested: `make demo-cloud` → BLOCKED decision with exit 0
- [ ] Error responses follow standard envelope (`error.code` present on all 4xx/5xx)
- [ ] `/v1/version` returns correct version string

---

## CI/CD

- [ ] `make check` passes (lint + typecheck + unit tests)
- [ ] Integration test suite passes with real Postgres + Redis
- [ ] Migration round-trip CI passes (upgrade → downgrade → upgrade)
- [ ] Docker build smoke test passes (`import keel.main` in runtime image)
- [ ] Auto-merge workflow tested: PR with `ready-to-merge` label merges automatically after CI
- [ ] Release workflow tested: tag `v*` creates GitHub Release with CHANGELOG
- [ ] Rollback procedure documented and tested:
  - [ ] `alembic downgrade -1` tested in staging
  - [ ] Old image can be deployed without schema changes

---

## Documentation

- [ ] [Getting Started](../getting-started.md) reviewed by non-engineer
- [ ] [API Reference](../api-reference.md) matches actual endpoint behavior
- [ ] [Authentication](../authentication.md) covers all error cases
- [ ] [Deployment](../deployment.md) tested by clean-room deployment
- [ ] [Troubleshooting](../troubleshooting.md) covers top 5 known issues
- [ ] [Security](../security.md) reviewed by security-aware team member

---

## Sign-Off

| Area | Owner | Status |
|:-----|:------|:-------|
| Security | — | ☐ |
| Infrastructure | — | ☐ |
| Product | — | ☐ |
| CI/CD | — | ☐ |
| Documentation | — | ☐ |

Beta is **approved to open** when all items above are checked and all owners have signed off.
