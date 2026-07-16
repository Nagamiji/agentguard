#!/usr/bin/env bash
# Refuses a direct push to `main`.
#
# This exists because GitHub will not enforce branch protection on a private repo without
# a paid plan (docs/branch-protection.md). Server-side, `main` is currently wide open, so
# this local hook is the only thing standing between a reflexive `git push` and an
# unreviewed commit on the production branch.
#
# It is a seatbelt, not a lock: it runs only on machines where `make hooks` was run, and
# `--no-verify` skips it. Delete it the day real branch protection is switched on.
set -euo pipefail

# pre-commit exports the ref being pushed TO on the pre-push stage.
target="${PRE_COMMIT_REMOTE_BRANCH:-}"

# Nothing to check (e.g. hook invoked outside a push) — stay out of the way.
[ -z "$target" ] && exit 0

if [ "$target" = "refs/heads/main" ] || [ "$target" = "main" ]; then
  cat >&2 <<'EOF'

✖ Direct push to `main` blocked.

  main only changes through a reviewed, squash-merged pull request:

      git switch -c feature/<name>
      git push -u origin feature/<name>
      gh pr create

  If you are certain (e.g. the one-off sync of already-reviewed history):

      git push --no-verify origin main

  Why this is a local hook and not GitHub's own protection:
  docs/branch-protection.md — private repos need a paid plan to enforce it.
EOF
  exit 1
fi
