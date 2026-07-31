# Current State Analysis

## What exists today

The current AgentGuard repository is an "AI security scanner" and deployment gate platform built around a control plane (FastAPI) and workers.
- **Control Plane (`src/keel`)**: Multi-tenant FastAPI application, Postgres database (with RLS), authentication, metrics, rate limiting.
- **Evaluation Engine (`src/keel/evals`)**: A deterministic execution engine that checks agents against failure scenarios, including prompt injection, data exfiltration, etc. Supports live execution against Vertex/Gemini.
- **Fingerprinting (`src/keel/fingerprint.py`)**: A system to track agent configurations by hashing their manifest components.
- **Policy Engine (`src/keel/policy`)**: Scoped rules (e.g. `max_tool_arg: $100`) compiled and enforced on scans.
- **CLI (`cli/src/agentguard_cli`)**: A standalone client connecting to the control plane, outputting SARIF, HTML, and JSON reports. Intended for use in CI as a merge gate.

## What should survive

- **Agent Behavior Record (Fingerprinting)**: The core idea of identifying an exact agent configuration (`prompt_hash`, `tool_schema_hash`, etc.) is essential for reproducing behavior.
- **Evaluation Engine (Core)**: The ability to execute tools and prompts consistently and capture their results as evidence.
- **Scenario Format**: The scenario structure can be generalized into a community-friendly YAML format.
- **CLI Shell**: The command-line architecture in `cli/src/agentguard_cli` can be heavily adapted to be the primary interface, completely localized rather than talking to a SaaS backend.
- **Security Library**: Will survive as a standalone package (`agentguard-security`).

## What should be removed

- **Centralized Control Plane & Database**: FastAPI app, Postgres dependencies, RLS, user authentication, tenant provisioning, and billing logic. This conflicts with the local-first "git-like" workflow.
- **Cloud Workers (Redis)**: Asynchronous Redis workers are unnecessary for a local-first workflow tool.
- **SaaS Features**: Complex team RBAC, rate-limiting, centralized policy compilation.
- **Mandatory Server Dependency**: Developers should not need to host a server or configure `AGENTGUARD_API_KEY` to take snapshots and diffs.

## What should be renamed

- The entire project shifts its identity from an "AI security scanner" to an "AI agent behavior engineering toolkit".
- The existing evaluations (`keel/evals/library`) should be factored into an `agentguard-security` plugin/package.
- `keel/evals` -> `agentguard.core` (or similar engine naming).

## What can become the new foundation

- The new foundation will be the local CLI and a local `.agentguard/` directory (similar to `.git/`).
- The `fingerprint` module will be adapted to generate local snapshot identifiers.
- The `agentguard_cli` becomes the main entry point (handling `init`, `snapshot`, `diff`, `test`).
- The `runner.py` logic from `keel/evals` becomes the execution engine for capturing `Agent Behavior Records`.
