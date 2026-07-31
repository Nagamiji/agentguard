# CI/CD Automation Security Review

This document provides a security review of the automated merge and release workflows implemented in Phase 9.

---

## 1. Auto-Merge Workflow Security Review

### Permission Scopes
The `.github/workflows/auto-merge.yml` requires:
- `pull-requests: write`: Needed to authorize the `gh pr merge` command.
- `contents: write`: Needed to merge commits into the `main` branch and delete the feature branch.
These scopes are the minimum necessary permissions for auto-merging.

### Fork PR Protection
- **Vulnerability**: If external PRs from repository forks triggered auto-merge, a malicious actor could submit a PR containing a payload, apply/simulate a label, and force a merge.
- **Mitigation**: The workflow includes the explicit condition:
  `github.event.pull_request.head.repo.full_name == github.repository`
  This ensures the PR head repository matches the parent repository, completely blocking fork PRs from executing the auto-merge job.

### Branch Protection Compliance
- **Vulnerability**: Auto-merge bypassing status checks or required reviews.
- **Mitigation**: The workflow utilizes GitHub's native `gh pr merge --auto` command. This does not force-merge the PR immediately. Instead, it instructs GitHub to flag the PR for merging *only after* all branch protection constraints (reviews, checks, approvals) are fully satisfied.

---

## 2. Release Workflow Security Review

### Execution Integrity
- **Trigger**: The release workflow is triggered using `workflow_run`:
  ```yaml
  on:
    workflow_run:
      workflows: ["CI"]
      branches: [main]
      types: [completed]
  ```
  This is highly secure because:
  1. It triggers only after the CI run on the `main` branch finishes.
  2. The job runs only if `github.event.workflow_run.conclusion == 'success'`, guaranteeing that failing commits on `main` can never generate a release artifact.

### Collisions & Duplicate Releases
- **Vulnerability**: Re-running a workflow or pushing the same version tag could fail or overwrite an existing release.
- **Mitigation**: The script checks if the tag already exists in the repository using `git rev-parse`. If the tag exists, it appends the commit short-SHA (e.g. `v0.9.1-abcdefg`) to guarantee uniqueness and prevent release failure.

---

## 3. Local Status Checker (`make status`)

- **Vulnerability**: Accidentally executing costly Vertex AI live model tests or slow database tests during local checks.
- **Mitigation**:
  1. Live Vertex tests require `RUN_VERTEX_EVAL=true` to be set explicitly; otherwise they are skipped.
  2. Integration tests are skipped automatically if Postgres/Redis are not active on local ports.
  3. We configure `make status` to explicitly ignore heavy integration test files, restricting status testing to fast, stateless unit checks.
