#!/usr/bin/env bash
# Enforces Conventional Commits on the PR TITLE, and warns on individual commit subjects.
#
# Only the title is a hard failure, because `main` is squash-merge-only: the PR title
# becomes the single commit on `main` and drives release notes, while the branch's own
# commit subjects are discarded by the squash. Failing a PR over a subject that will
# never reach `main` would just punish work-in-progress commits.
set -euo pipefail

# type(optional-scope)!: subject   — e.g. "feat(api): add agent registry"
# Scope is free-form, so a backlog ID doubles as one: "feat(be-02): add agent registry".
PATTERN='^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: .+'

usage() {
  cat <<'EOF'

Conventional Commit format required:
  <type>[optional scope][!]: <subject>

  types: feat fix docs style refactor perf test build ci chore revert
  '!' marks a breaking change.

  A backlog ID fits naturally as the scope:
    feat(be-02): add agent registry endpoint
    fix(db): scope project lookup to the caller's org
    ci!: require the gate check before merge
EOF
}

if [[ ! "${PR_TITLE}" =~ $PATTERN ]]; then
  echo "::error::PR title is not a Conventional Commit: '${PR_TITLE}'"
  echo "::error::It is squash-merged onto main verbatim, so it must match."
  usage
  exit 1
fi

# Advisory only — see the header. Never exits non-zero.
while IFS= read -r subject; do
  [ -z "$subject" ] && continue
  case "$subject" in "Merge branch "*|"Merge pull request "*) continue ;; esac
  if [[ ! "$subject" =~ $PATTERN ]]; then
    echo "::warning::commit subject is not a Conventional Commit (squashed away, not blocking): '$subject'"
  fi
done < <(git log --no-merges --format=%s "${BASE_SHA}..${HEAD_SHA}")

echo "PR title OK: ${PR_TITLE}"
