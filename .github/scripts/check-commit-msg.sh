#!/usr/bin/env bash
# pre-commit `commit-msg` hook: reject a non-Conventional commit at write time, so the
# gate is not the first thing to mention it. Same grammar as the CI check
# (.github/scripts/check-conventional-commits.sh) — keep the two patterns in step.
set -euo pipefail

msg_file="$1"
# First non-comment, non-empty line is the subject.
subject="$(grep -v '^#' "$msg_file" | sed '/^[[:space:]]*$/d' | head -n1 || true)"

# Let git's own machinery (merge/revert/fixup) through untouched.
case "$subject" in
  "Merge "*|"Revert "*|"fixup!"*|"squash!"*) exit 0 ;;
esac

PATTERN='^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: .+'

if [[ ! "$subject" =~ $PATTERN ]]; then
  cat >&2 <<EOF
✖ Not a Conventional Commit:

    $subject

  format: <type>[optional scope][!]: <subject>
  types:  feat fix docs style refactor perf test build ci chore revert

  examples:
    feat(api): add agent registry endpoint
    fix(db): scope project lookup to the caller's org
EOF
  exit 1
fi
