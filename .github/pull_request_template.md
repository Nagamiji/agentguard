<!--
PR title MUST be a Conventional Commit — it becomes the squash commit on main.
  e.g. feat(api): add agent registry endpoint
-->

## What & why

<!-- What changes, and what problem it solves. Link the backlog task: BE-02, AI-01, ... -->

## Prime-directive check

<!-- CLAUDE.md: "a developer can connect an agent → run reliability tests in CI → get a
     failure report → block the deploy." How does this move that forward? -->

## How I verified

<!-- What you actually ran/observed, beyond "CI is green". -->

## Checklist

- [ ] `make check` passes locally (lint + typecheck + tests)
- [ ] No secrets in code — config via `KEEL_*` env vars
- [ ] Tenant isolation preserved (new tables have RLS; new queries are org-scoped)
- [ ] Migrations are reversible, and tested against a real database
- [ ] Docs/`CLAUDE.md` updated if behaviour or workflow changed
- [ ] Deviations from the standard stack have a TDR in the OS repo (`../keel`)

## Risk & rollback

<!-- What could break, and how to undo it. "None" is an answer — but say it deliberately. -->

---
<!-- Maker ≠ Checker: the author does not merge their own PR. A human reviews, then merges. -->
