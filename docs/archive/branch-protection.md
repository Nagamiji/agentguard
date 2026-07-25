# Branch protection & the merge gate

How `main` is protected, why each setting is what it is, and how to change it.

> ## ⚠️ Status: NOT ENFORCED (2026-07-16)
>
> `make protect` currently fails with **HTTP 403 — "Upgrade to GitHub Pro or make this
> repository public"**. GitHub restricts protected branches *and* rulesets to paid plans
> for **private** repositories, and `Nagamiji/agentguard` is private on the free plan.
> This is a plan limit, not a misconfiguration.
>
> **What this means right now:** CI runs on every PR and reports pass/fail, but **nothing
> stops a merge or a direct push to `main`.** The gate is *advisory*. A green ✅ is
> information, not enforcement — the discipline is currently in the humans, not the
> platform.
>
> **To make it real, pick one:**
>
> | Option | Cost | Trade-off |
> |---|---|---|
> | GitHub Pro | ~$4/month | Repo stays private; everything below starts working. Re-run `make protect`. |
> | Make repo public | free | Protection works immediately, but the code is world-readable — this is the product. |
> | Stay as-is | free | Gate stays advisory. Acceptable only while a single disciplined maintainer is the only committer. |
>
> **Decision (2026-07-16):** option 3 — the gate stays **advisory** for now.
>
> What *is* enforced today (these are free): squash-merge only, merge commits and rebase
> merges disabled, auto-merge disabled, branches deleted on merge.
>
> **Compensating control:** `make hooks` installs a local `pre-push` hook
> (`.github/scripts/pre-push-guard.sh`) that refuses a direct push to `main`. It is a
> seatbelt, not a lock — it only exists on machines where `make hooks` ran, and
> `--no-verify` skips it. It cannot stop a merge through the GitHub web UI. Delete it when
> real protection is switched on.

Apply or re-apply protection with:

```bash
gh auth login                              # once; needs admin on the repo
make protect                               # → scripts/apply-branch-protection.sh
```

## What "auto merge" does and does not mean here

Green CI **enables** the merge button. It does not press it.

This is deliberate and it is the one rule the rest of the setup hangs off
(`CLAUDE.md`: *Maker ≠ Checker; human gate on every merge*). CI proves the code passes
the engineering gates. It cannot tell you the change was the *right* change, that the
migration is safe against real data, or that a plausible-looking test actually tests
anything. When Claude is the maker, a human is the only checker in the loop — an
auto-merge on green would remove the last one.

So `allow_auto_merge` is **off** at the repository level. Turning it on is a policy
decision, not a settings tweak: it contradicts `CLAUDE.md`, which would have to change
first.

## The settings

| Setting | Value | Why |
|---|---|---|
| Required status check | `gate` only | One fan-in job (`.github/workflows/ci.yml`) depends on every other job. New CI jobs need no protection change. |
| Strict (up-to-date) | on | A PR must be rebased on current `main` before merging. Stops the "both green apart, broken together" merge. |
| Required approvals | 1 | The human checker. |
| Code-owner review | on | Routes security-critical paths to an owner (`.github/CODEOWNERS`). |
| Dismiss stale reviews | on | A new push invalidates the old approval — otherwise "approved" can describe code nobody read. |
| Linear history | on | Squash-only merges; `main` stays bisectable. |
| Force pushes / deletions | off | `main` history is append-only. |
| Conversation resolution | on | Review comments get answered, not outrun. |
| Enforce admins | **off** (for now) | See below. |

### Why `enforce_admins` is off

With a single maintainer, `enforce_admins=true` plus a required approval is a deadlock:
GitHub does not let you approve your own pull request, so any PR **you** authored could
never merge — and the escape hatch would be disabling protection under pressure, which is
worse than never having had it.

Off means the gate governs the normal path while leaving the owner an explicit,
audited override. This is a real weakening of the rule and it is written down here rather
than hidden in a settings page.

**Flip it on the day a second human can review:**

```bash
ENFORCE_ADMINS=true bash scripts/apply-branch-protection.sh
```

Note the asymmetry that makes this workable today: PRs authored by **Claude** already get
a genuine maker≠checker split, because you review them. Only your own PRs lack a second
pair of eyes.

## The flow

```
feature/*  →  commit  →  Pull Request
                              │
                              ▼
                     GitHub Actions (gate)
                     ├── ruff          (lint + format)
                     ├── mypy --strict (types)
                     ├── pytest        (unit, no DB)
                     ├── pytest + RLS  (integration, Postgres service)
                     ├── security      (gitleaks + pip-audit)
                     ├── docker        (image builds + imports)
                     ├── terraform     (fmt + validate)
                     └── commit-style  (Conventional Commits)
                              │
                        all green → merge button unlocks
                              │
                              ▼
                     human review + approval   ← the gate CI cannot replace
                              │
                              ▼
                            main
                              │
                              ▼
                    release.yml → deployment artifact
```

## Branch strategy

- **`main`** — protected, always releasable. Only ever changed by a squash-merged PR.
- **`feature/*`** — all development. Short-lived; deleted on merge.
- Everything else (`fix/*`, `chore/*`) follows the same rules; the prefix is a label, not
  a mechanism.

## Changing the gate

A PR that weakens CI is a policy change, and `.github/` is code-owned so it needs owner
review. Say plainly in the PR description what protection is being reduced and why. The
gate is only worth anything if loosening it is harder than fixing the code.

## Verifying protection is live

```bash
gh api repos/Nagamiji/agentguard/branches/main/protection --jq '.required_status_checks'
```

The honest test is behavioural: open a throwaway PR that breaks lint on purpose and
confirm the merge button stays disabled. Protection that has never been observed to block
anything is a guess, not a guarantee.
