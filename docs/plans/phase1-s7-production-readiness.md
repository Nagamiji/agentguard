# Phase 1 · S7 Tenant-Provisioning Production Readiness

**Planning only — no code.** Founder decision (001): keep the `X-Provisioning-Key`
guard as a **bridge**; add invitation tokens + scoped bootstrap creds + audit trail;
move to identity-first onboarding before GA.

This doc is an **audit of the existing implementation** (per "verify before you
change") plus the checklist to make it production-ready. Findings are graded and
cite `file:line`.

## Status
S7 is implemented on `fix/s7-tenant-bootstrap-protection` (`8d4d3ae`), tested, and
**not yet merged to `main`**. The core guard is sound; the gaps are in
*deployment wiring*, *telemetry*, and one *adjacent least-privilege* path.

## Security audit
| Check | Result | Evidence |
|---|---|---|
| Provisioning auth enforced before authz | ✅ | `provisioning_guard` dep on both endpoints — `api/orgs.py:32,144` |
| Fail-closed when secret unset (prod) | ✅ 503 in prod, dev-only open | `provisioning.py:83-88` |
| Fail-closed when limiter store down | ✅ 503 (deliberately, unlike scan limiter) | `provisioning.py:102-107` |
| Constant-time secret compare | ✅ `hmac.compare_digest` | `provisioning.py:75-77` |
| Secrets from env, never hardcoded, empty default | ✅ | `config.py:59` (`onboarding_secret=""`) |
| Bootstrap key least-privilege (no `*`) | ✅ `/orgs`→admin explicit, `/onboarding`→developer | `api/orgs.py:57,165` |

**The guard itself passes.** The problems are around it:

### Findings
- **F1 · HIGH · Secret not wired in IaC.** `KEEL_ONBOARDING_SECRET` appears in **no**
  Terraform, tfvars, or workflow (`infrastructure/terraform/*.tf`, `.github/workflows/*`).
  Consequence: in prod the fail-closed default returns **503 on all onboarding**
  until the secret is set by hand — safe, but broken onboarding, and nothing asserts
  it's set. *Action:* add the secret to the secret manager + Terraform env wiring;
  add a startup log-assertion that warns if a prod build has provisioning reachable
  without a secret.
- **F2 · MEDIUM · Per-IP limit is XFF-spoofable.** `_client_ip` trusts the first
  `X-Forwarded-For` hop with no trusted-proxy allowlist (`provisioning.py:63-67`);
  the code documents this. An attacker rotating XFF evades the per-IP token bucket.
  *Action:* configure a trusted-proxy hop count / real peer IP; the secret remains
  the primary control, this is defence-in-depth hardening.
- **F3 · MEDIUM · Authenticated key path still defaults to wildcard.** `POST
  /orgs/keys` mints a full-access `["*"]` key when both `role` and `scopes` are
  omitted (`schemas.py:114-116`, "Backward-compatible default: a full-access key";
  `api/orgs.py:80`). S7 fixed the *unauthenticated bootstrap* paths, not this one.
  *Action (needs founder approval — breaking):* default to least-privilege or
  require an explicit role/scopes. Flag for the invitation-token/scoped-cred work.
- **F4 · MEDIUM · Provisioning emits no telemetry.** The guard logs/audits/meters
  nothing on 403/429/503 (`provisioning.py` has no log/metric/audit call). S7 abuse
  attempts are invisible. *Action:* emit a structured security event + a metric +
  an audit row on each rejection. **Shared with the observability plan.**

## Deployment checklist
- [ ] `KEEL_ONBOARDING_SECRET` provisioned in the secret manager (F1).
- [ ] Terraform passes it to the app env; `KEEL_ONBOARDING_RATE_LIMIT_PER_HOUR` set.
- [ ] Confirm `KEEL_APP_ENV` is `prod`/`production`/`staging` in deployed envs (drives
      the fail-closed branch — `provisioning.py:31,84`).
- [ ] Startup assertion / healthcheck surfaces "provisioning disabled: no secret".
- [ ] Trusted-proxy config for real client IP behind the load balancer (F2).

## Abuse-protection checklist
- [x] Per-IP token bucket, fail-closed (`provisioning.py:91-113`).
- [ ] XFF trust boundary fixed (F2).
- [ ] Rejection telemetry so 429/503 spikes are visible (F4 → observability alerts).

## Authorization checklist
- [x] Bootstrap keys least-privilege, no `*` (`api/orgs.py:57,165`).
- [x] Tenant isolation via RLS + non-superuser app role (`config.py:20-24`).
- [ ] Close the wildcard-default on the authenticated key path (F3).

## Testing checklist
Existing coverage in `tests/test_provisioning.py` (per `8d4d3ae`): anon rejected
when secret set · valid secret succeeds · wrong secret rejected · prod-without-secret
disabled · dev allowed · onboarding key forbidden on admin routes · bootstrap key can
manage keys · per-IP limit enforced.

**Positive (have):** valid provisioning succeeds · correct scoped key generated.
**Negative — add:**
- [ ] XFF spoof does **not** reset the per-IP bucket (F2 regression test).
- [ ] Key issued with no role/scopes is **not** wildcard (F3 — after the fix).
- [ ] Each rejection emits a security event/metric/audit row (F4).
- [x] missing/wrong secret rejected · prod-without-secret disabled · rate limit triggers.

## Phase-1 scope vs backlog
- **Phase 1 (this cycle):** merge S7; F1 (secret wiring) + startup assertion; F4
  (rejection telemetry); F2 (trusted proxy).
- **Backlog (founder roadmap, pre-GA):** invitation tokens → scoped bootstrap creds →
  identity-first onboarding; F3 wildcard-default change (breaking — approval needed).
