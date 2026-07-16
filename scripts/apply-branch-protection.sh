#!/usr/bin/env bash
# Applies branch protection to `main`. Protection lives in GitHub's settings API, not in a
# workflow file, so this script is the closest thing to "protection as code" — run it
# instead of clicking through Settings, and keep changes reviewable in git.
#
#   gh auth login          # once, needs admin on the repo
#   bash scripts/apply-branch-protection.sh
#
# Read docs/branch-protection.md before changing any value here.
set -euo pipefail

REPO="${REPO:-Nagamiji/agentguard}"
BRANCH="${BRANCH:-main}"

# The ONE required check: `gate` fans in on lint/typecheck/unit/integration/security/
# docker/terraform/commit-style (.github/workflows/ci.yml). Listing sub-jobs here instead
# would mean editing protection every time CI gains a job.
REQUIRED_CHECK="${REQUIRED_CHECK:-gate}"

# Admin bypass. Default false: with one maintainer, `enforce_admins=true` + a required
# approval is a deadlock — GitHub forbids approving your own PR, so a PR you authored
# could never merge. False keeps the gate on for the normal path while leaving the owner
# an explicit, audited override. Set ENFORCE_ADMINS=true once a second human can review.
ENFORCE_ADMINS="${ENFORCE_ADMINS:-false}"

command -v gh >/dev/null || { echo "error: gh CLI not installed"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: run 'gh auth login' first"; exit 1; }

echo "Applying protection to ${REPO}:${BRANCH} (enforce_admins=${ENFORCE_ADMINS})"

# GitHub gates branch protection AND rulesets behind a paid plan for PRIVATE repos.
# Fail with the actual remedy rather than a raw 403 the reader has to decode.
#
# Capture the probe's output instead of piping it to grep: `pipefail` is set, so a
# `gh ... | grep` pipeline reports gh's own 403 exit status even when grep matches,
# and the check would silently never fire.
probe="$(gh api "repos/${REPO}/branches/${BRANCH}/protection" 2>&1 || true)"
if [[ "$probe" == *"Upgrade to GitHub Pro"* ]]; then
    cat >&2 <<EOF

✖ Branch protection is unavailable: ${REPO} is PRIVATE on a free plan.
  GitHub restricts protected branches and rulesets to Pro/Team/Enterprise for
  private repos. This is a plan limit, not a config error.

  Options:
    1. GitHub Pro (~\$4/mo)  — keeps the repo private, protection works. Then re-run.
    2. Make the repo public — protection is free, but the code becomes world-readable.
    3. Stay as-is           — CI still RUNS on every PR and reports pass/fail; it just
                              cannot BLOCK a merge. The gate is advisory until this is
                              resolved. Do not mistake a green check for enforcement.

  See docs/branch-protection.md.
EOF
  exit 2
fi

gh api -X PUT "repos/${REPO}/branches/${BRANCH}/protection" \
  -H "Accept: application/vnd.github+json" \
  --input - <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["${REQUIRED_CHECK}"]
  },
  "enforce_admins": ${ENFORCE_ADMINS},
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true,
  "block_creations": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON

# Squash-only: the PR title is the Conventional Commit that lands on main, which is what
# .github/scripts/check-conventional-commits.sh validates and what release notes read.
echo "Setting merge strategy (squash only, auto-merge disabled)"
gh api -X PATCH "repos/${REPO}" \
  -f allow_squash_merge=true \
  -f allow_merge_commit=false \
  -f allow_rebase_merge=false \
  -f allow_auto_merge=false \
  -f delete_branch_on_merge=true \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=PR_BODY \
  >/dev/null

echo
echo "Done. Current protection:"
gh api "repos/${REPO}/branches/${BRANCH}/protection" \
  --jq '{
    required_checks: .required_status_checks.contexts,
    strict_up_to_date: .required_status_checks.strict,
    reviews: .required_pull_request_reviews.required_approving_review_count,
    code_owner_review: .required_pull_request_reviews.require_code_owner_reviews,
    enforce_admins: .enforce_admins.enabled,
    linear_history: .required_linear_history.enabled,
    force_pushes: .allow_force_pushes.enabled
  }'
