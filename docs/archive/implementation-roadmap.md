# Implementation Roadmap

## Phase 1: Snapshot + Diff
**Goal**: Build the core primitive and demonstrate the "Git for AI" workflow.
- Initialize the `.agentguard/` directory structure (`agentguard init`).
- Implement the local execution tracer to generate an Agent Behavior Record JSON (`agentguard snapshot`).
- Build the diffing engine to compare two snapshots and highlight material changes (tools, prompts, outputs) (`agentguard diff`).
- Validate with a simple Python agent script.

## Phase 2: Scenario Testing
**Goal**: Enable regression testing via community-friendly declarative scenarios.
- Define the YAML scenario format.
- Build the `agentguard test` command to run an agent against a directory of scenarios.
- Implement basic assertions (e.g., expected tool calls, expected outputs).

## Phase 3: Replay
**Goal**: Allow developers to replay a specific execution trace.
- Implement `agentguard replay <snapshot-id>` to load past context.
- Enable step-by-step debugging of agent decisions based on past records.

## Phase 4: Community Ecosystem
**Goal**: Foster open-source contribution.
- Standardize the plugin model for frameworks (LangChain, LlamaIndex, direct SDKs).
- Create a central repository/registry for community scenarios (e.g., customer support edge cases).
- Ensure the `Agent Behavior Record` is well-documented for third-party tooling.

## Phase 5: Security and Enterprise Packages
**Goal**: Bring back the legacy security capabilities as an opt-in layer.
- Release `agentguard-security` as an official plugin containing all OWASP ASI probes.
- Introduce enterprise management features (if requested by the community, though heavily separated from the core CLI).
