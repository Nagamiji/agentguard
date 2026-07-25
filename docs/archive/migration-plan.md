# Migration Plan

How current AgentGuard becomes the new platform.

## Keep
- **Agent Fingerprint Logic**: The content-addressed hashing (`prompt_hash`, `tool_schema_hash`, etc.) found in `keel/fingerprint.py` is the perfect foundation for identifying unique Agent Behavior Records.
- **Evaluation Runner**: The deterministic execution engine and tool interception logic (`keel/evals`) will be adapted into the local snapshot/tracing engine.
- **CLI Shell**: The command-line architecture in `cli/src/agentguard_cli` provides a good starting point for the new `agentguard` CLI.
- **Security Scenarios**: Existing probes (prompt injection, exfiltration, etc.) will be packaged into a separate `agentguard-security` repository/package.

## Modify
- **Target Audience & Positioning**: Pivot from a security gate to a general behavior workflow tool.
- **Data Storage**: Move away from a centralized Postgres DB towards a local `.agentguard/runs/` directory for storing JSON snapshots.
- **CLI Commands**: Overhaul the CLI to support git-like commands (`init`, `snapshot`, `diff`, `test`, `replay`).
- **Policy Engine**: Simplify the policy engine to run locally based on repository configuration rather than database-backed tenants.

## Remove
- **FastAPI Control Plane**: Delete the central server dependencies (`src/keel` API routes, Redis workers).
- **Postgres Database / Alembic Migrations**: Local execution means no central database is required.
- **SaaS Specifics**: Remove rate limiting, billing models, and centralized RBAC logic.
- **Heavy Dependencies**: Prune `pyproject.toml` to ensure the `agentguard` CLI is as lightweight as possible.
