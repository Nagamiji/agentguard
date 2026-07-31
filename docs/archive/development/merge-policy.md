# AgentGuard Merge and Release Policy

This document details the branch governance, CI/CD validation gates, auto-merge policies, and release workflows.

---

## 1. Branch Rules

- **`main` is protected**: Direct pushes to `main` are strictly forbidden. All changes must be proposed via Pull Requests (PRs).
- **Linear History**: Rebase feature branches on top of `main` before merging. No merge commits are allowed; all merges are squashed.
- **Branch Cleanup**: Feature branches are automatically deleted upon successful squash-merge.

---

## 2. CI/CD Validation Gates

Every Pull Request must pass the following mandatory checks executed by the `CI` workflow:

1. **Linting (`ruff`)**: Checks code style and ensures formatting conforms to standard repository limits (100 characters per line).
2. **Typechecking (`mypy`)**: Strict Python typechecking on the entire source tree.
3. **Unit Tests (`pytest`)**: Pytest runs exercising logical functions (excluding database-required tests).
4. **Integration Tests (Postgres + Redis)**: Database-required test suites verifying PostgreSQL Row-Level Security (RLS) and Redis-backed rate limiting.
5. **Security Scan**:
   - `gitleaks` checks history to prevent secret leaks.
   - `pip-audit` scans dependencies for known CVEs.
6. **Docker Build**: Builds the control plane image and executes an import smoke check.
7. **Terraform**: Validates infrastructure definitions.
8. **Conventional Commits**: Verifies that the PR title and commits conform to the conventional commits specification.

---

## 3. Automated Merge Policy

We employ a safe auto-merge pipeline to optimize development velocity while preserving gate safety:

- **Trigger**: Apply the `"ready-to-merge"` label to a Pull Request.
- **Auto-Merge Job**: The `auto-merge` workflow enables native GitHub auto-merge on squash.
- **Execution**: The PR is held in queue until all CI checks successfully complete. Once green, the PR is squashed, merged, and the branch is deleted automatically.
- **Drafts and Forks**: Auto-merge is bypassed for draft PRs and completely blocked for external forks to prevent secret exposure.

---

## 4. Release Automation

Once a PR merges into `main` and the final CI check on `main` is successful:
1. A release workflow is triggered to build the production Docker image.
2. The version is extracted from `pyproject.toml`.
3. A Git tag (e.g. `v0.9.1`) is created and pushed.
4. A GitHub Release is created, attaching the image tarball and automated release notes.
