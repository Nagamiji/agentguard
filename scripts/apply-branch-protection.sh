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
