# Spec · Remove the implicit wildcard-scope default on key creation

**Status: SPEC ONLY — no code, awaiting founder approval.** Selected as the single
highest-value next task after re-evaluating current `main` (S7 merged; prod infra
absent — see rationale). Breaking API change → needs your sign-off before a branch.

## Why this task (re-evaluation of current state)
- **S7 (#22) is merged; `main` is protected** against anonymous org/key minting. But
  S7 explicitly "dropped wildcard keys" only on the *bootstrap* paths. The
  **authenticated** `POST /orgs/keys` still mints a full-access `["*"]` key when the
  caller omits both `role` and `scopes` (`schemas.py:114-116` — "Backward-compatible
  default: a full-access key"; used at `api/orgs.py:80`). That least-privilege defect
  is **live on `main` now** and is the direct completion of the S7 theme.
- **The founder's Phase-1A #1 (wire `KEEL_ONBOARDING_SECRET` into Terraform) is
  currently blocked:** `infrastructure/terraform/main.tf` is a skeleton ("Real
  modules land in PLAT-01… commented until PLAT-01 wires real providers"). There is
  no app-service, no secret manager to wire into yet. Secret wiring belongs to
  PLAT-01, with every other secret — not now.
- This task is **pure application code, no infra dependency, small, testable**, and
  raises the security floor immediately. It is the best "one task per iteration" unit.

## Technical design
Change the scope-resolution default in `ApiKeyCreate.resolve_scopes`
(`schemas.py:108-117`). Today:
```python
elif self.scopes is None:
    self.scopes = ["*"]   # silent full-access default
```
**Recommended (Option A — reject implicit privilege):** if both `role` and `scopes`
are omitted, raise a validation error → `422` with a clear message
("Provide a 'role' or explicit 'scopes'"). No key is ever minted with implicit
authority. Matches the founder's "require explicit scopes."

**Alternative (Option B — least-privilege default):** default to `viewer` (`["read"]`)
when both omitted. Non-rejecting, but changes granted scopes. Weaker guarantee (a
caller can still be surprised), so A is preferred.

Either way: **explicit** `scopes=["*"]` or `role="owner"` remains allowed — a
deliberate, audited wildcard is legitimate (org bootstrap). Only the *silent default*
is removed. `dead-code` fallback `["*"]` at `api/orgs.py:80` is deleted.

## Architecture impact
Minimal and localized. Enforcement stays on scopes (`deps.py`), unchanged. Roles
(`roles.py`) unchanged. No new dependency, no new endpoint, no DB change. The API
contract for `POST /orgs/keys` gains a required "role-or-scopes" precondition.

## Affected files
- `src/keel/schemas.py` — `ApiKeyCreate.resolve_scopes` (the change) + docstring.
- `src/keel/api/orgs.py:80` — remove the dead `["*"]` fallback (now unreachable).
- `tests/test_rbac.py`, `tests/test_provisioning.py` — add cases (below). Existing
  cases already pass explicit `role`/`scopes`, so they stay green.
- `docs/` — any API doc stating the default scope (grep `orgs/keys`).
- **No DB migration.**

## Migration plan
- **Blast radius (audited): near-zero internally.** Bootstrap → explicit admin
  (`api/orgs.py:57`); onboarding → `developer`; every `/orgs/keys` test passes an
  explicit `role`/`scopes`; no caller relies on the implicit wildcard.
- **External:** any consumer POSTing `/orgs/keys` with neither field now gets `422`
  instead of a wildcard key. Pre-GA (DO-01, no prod) → negligible. Document in the
  changelog/PR as a **breaking change**.
- **CLI package check:** the standalone `agentguard` CLI lives in its own repo/package
  — verify it never creates keys without scopes before release alignment.
- Rollout: single PR; no phased migration needed (behavior change, not data).

## Testing strategy
- **Positive:** `role="ci"` → `["read","scan"]`; explicit `scopes=["read","write"]`
  → those; `role="owner"` → `["*"]` still works (deliberate wildcard preserved).
- **Negative / the guarantee:** `{"name":"x"}` (no role, no scopes) → **422**, and
  **no key row created**. `role` + `scopes` together → 422 (already enforced,
  `schemas.py:110`). invalid scope → 422 (already).
- **Regression:** full `tests/test_rbac.py` + `tests/test_provisioning.py` stay green.
- `make check` (ruff + mypy --strict + unit + integration) green before PR.

## Rollback strategy
Single-commit revert restores the prior default. No data migration to unwind (stored
keys are unaffected — only creation-time behavior changed). Zero-downtime either way.

## Edge cases
- `scopes=[]` (explicit empty) → currently accepted as a zero-access key. Decide:
  reject with a clear message (recommended — an empty-scope key is almost surely a
  mistake) or allow (harmless but useless). Spec leans **reject empty**.
- `role="owner"` / explicit `["*"]` → still allowed (intended). Consider a **follow-up**
  (out of scope here): require the caller to hold `admin` to mint `owner`/`*` keys —
  defense in depth. Note only; not this task.
- Unknown role / unknown scope → already 422 (`schemas.py:97,104`).

## Security considerations
- **Strictly improves least-privilege**: no credential is ever issued with more
  authority than the caller explicitly chose. Removes a silent privilege-escalation
  footgun (a key minted "just with a name" today can do *everything, including any
  future scope*).
- Preserves auditable explicit wildcard for legitimate bootstrap; the endpoint is
  already admin-gated (`AdminOrg`), so only admins reach it.
- Pairs naturally with the eventual invitation-token / identity-first onboarding work
  (001) but does not depend on it.

## Acceptance criteria
1. `POST /orgs/keys` with neither `role` nor `scopes` → `422`, **no** key created.
2. No code path can mint a wildcard key *implicitly*; `["*"]` only via explicit
   `role="owner"` or `scopes=["*"]`.
3. Explicit `role`/`scopes` behavior unchanged; all existing RBAC tests green.
4. New negative tests assert (1) and (2); `make check` green.
5. PR labelled breaking-change; changelog notes the required-scopes precondition.

## Open decision for founder
- **Option A (reject) vs Option B (default viewer)** — recommend **A**.
- Reject empty `scopes=[]`? — recommend **yes**.
- Include the "owner/`*` requires admin" defense-in-depth follow-up now, or defer? —
  recommend **defer** (keep this task tight).
