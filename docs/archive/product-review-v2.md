# Product Review V2

## 1. Executive Summary
AgentGuard is pivoting from an AI security scanner (with a heavy centralized backend) to a local-first, developer workflow platform. The new primitive is the **Agent Behavior Record**. The core value proposition is enabling developers to treat AI agent behavior like software changes, catching regressions locally before deployment. The architecture must aggressively drop its SaaS origins (FastAPI, Postgres, Redis) in favor of a lightweight CLI.

## 2. Product Thesis
AI agents are highly stochastic, making traditional unit tests insufficient and brittle. While existing tools (LangSmith, Langfuse) provide excellent post-deployment observability, there is a massive gap in the local, pre-commit workflow. Developers need a deterministic way to answer: *"If I change this prompt or tool, what is the blast radius on my agent's behavior?"*
AgentGuard fills this gap by acting as the "Git + pytest + Terraform plan" for AI agent behavior.

## 3. Target User
**Startup AI Engineer**
- **Why?** Solo developers might not have enough complex edge cases to care yet, and enterprise platform teams move too slowly and demand compliance features (RBAC, SSO). Startup engineers are shipping agents to production rapidly, feeling the acute pain of regressions ("I tweaked the prompt and now the refund tool is broken"), and are highly motivated to adopt lightweight CLI tools that integrate into GitHub Actions immediately.

## 4. Core Workflow
### The Painful Problem
"I changed my system prompt to make the agent sound friendlier and upgraded to `gpt-4o`. I don't know if my agent still properly refuses unauthorized refund requests. I have to manually test it in the chat UI."

### The Equivalent Workflow
- **pytest**: `agentguard test` (run the agent against community or local scenarios).
- **git**: `agentguard diff` (see the material changes between two Agent Behavior Records).
- **terraform**: `agentguard diff` acts as the "plan", showing the blast radius before the code is merged.

### The Smallest Useful Product
**`agentguard diff`**
- **Input**: Two `agent-record.json` snapshots (or a baseline snapshot vs. current uncommitted state).
- **Output**: A terminal-based, git-like diff highlighting changes in Model (e.g. `gpt-4` -> `gpt-4o`), Tool usage (e.g. `refund()` used instead of `escalate()`), and Output strings.
- **Why run it every day?** Because it provides immediate confidence that a prompt tweak didn't cause a catastrophic regression in core behavior, acting as the ultimate pre-commit check.

## 5. Architecture Recommendation

### Agent Behavior Record (`agent-record.json`)
- **Mandatory Fields**: `schema_version`, `agent_id`, `fingerprint` (hashes of prompt, tools, model), `input`, `tool_calls`, `output`.
- **Optional Fields**: `latency`, `cost`, `evaluation` (test assertions).
- **NEVER Stored**: PII, real user session data (snapshots should be synthetic/scenarios), and raw authentication tokens (API keys).

### Framework Strategy
We build three layers to ensure we don't force a specific framework:
1. **Layer 1 (Manual)**: `@agentguard.record` decorator for custom Python/TS agents.
2. **Layer 2 (Auto-tracing)**: Adapters for OpenAI SDK, LangChain, etc.
3. **Layer 3 (Universal Export)**: The moat. Any framework can just export `agent-record.json`.

### Architecture Critique
- **KEEP**: The fingerprinting logic (`keel/fingerprint.py`) and the deterministic evaluation runner (`keel/evals`).
- **MODIFY**: The CLI heavily. It must become a local engine, not just a thin client to an API.
- **REMOVE**: The FastAPI backend, Postgres database, Redis workers, and user authentication. They are dead weight for a local developer tool.

## 6. Open-Source Ecosystem Model
The ecosystem will be modeled after OpenTelemetry (standardized formats) and pytest (plugin ecosystem).
- **Structure**: `community/scenarios/`, `community/adapters/`, `community/reporters/`.
- **Contribution**: Developers contribute YAML scenarios (e.g., `scenarios/security/prompt-injection.yaml`) because they want to share edge cases and test their own agents against community-curated attacks.
- **Standardization**: If `agent-record.json` becomes the standard export format, third-party dashboards and observability tools will build native support for parsing AgentGuard snapshots.

## 7. Biggest Risks
1. **Scenario Quality**: Community scenarios might be brittle or flaky. We need strict schema validation and a core maintainer review process to prevent "bad" scenarios from polluting the ecosystem.
2. **Replay Feasibility**: Replaying stochastic agent behavior perfectly is incredibly difficult.
   - **Roadmap adjustment**: Phase 3 (Replay) should be delayed significantly. Focus entirely on Phase 1 (Snapshot + Diff) and Phase 2 (Scenario Testing).

## 8. Final Recommendation
**Do not build the SaaS backend.** Rip out the FastAPI and Postgres dependencies immediately.
AgentGuard must be a hyper-local, fast CLI tool. By owning the `agent-record.json` standard and the `agentguard diff` developer experience, we can build the foundational workflow tool for agent engineering.

We are ready to proceed with Phase 1: Snapshot + Diff.
