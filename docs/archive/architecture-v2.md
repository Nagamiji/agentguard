# Architecture V2

## System Design
AgentGuard V2 is a local-first, CLI-driven developer tool. It operates primarily in the user's filesystem, generating and comparing deterministic "Agent Behavior Records" stored as JSON files.

## Components
1. **CLI Interface**: The primary interaction point (`init`, `snapshot`, `diff`, `test`, `replay`).
2. **Snapshot Engine**: Captures the state of an agent (model config, tools, prompt hash) and records its behavior when run against a given scenario.
3. **Diff Engine**: Compares two Agent Behavior Records to highlight material changes in logic, tool usage, and output.
4. **Scenario Loader**: Reads `.yaml` scenarios from the local repository (and later community registries).
5. **Storage Layer**: A local `.agentguard/` directory containing the `runs/` history and configuration.

## Data Flow
1. Developer runs `agentguard snapshot app.py`.
2. The CLI intercepts the agent's execution, capturing the prompt, model, and tool definitions (generating a Fingerprint).
3. The Snapshot Engine runs the agent against defined default scenarios or ad-hoc inputs.
4. The execution trace (tool calls, inputs, outputs) is serialized into an Agent Behavior Record.
5. The Record is saved to `.agentguard/runs/run-<id>.json`.
6. When `agentguard diff` is called, the Diff Engine parses two JSON records and outputs a git-like summary of behavioral changes.

## Package Structure
- `agentguard.cli`: Command-line interface and parsing.
- `agentguard.core.snapshot`: The behavior capturing engine.
- `agentguard.core.diff`: The comparison and diffing logic.
- `agentguard.core.scenario`: YAML scenario parsing and management.
- `agentguard.integrations`: Wrappers for OpenAI, Anthropic, LangChain (Level 2 support).
- `agentguard_security`: (Separate package) The security-specific scenario library and evaluators ported from V1.
