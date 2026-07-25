# Product Direction

## Target Users
- Developers building AI agents (using frameworks like LangChain, Anthropic SDK, OpenAI SDK, or custom implementations).
- QA and Reliability Engineers responsible for ensuring AI agent behavior remains consistent.
- Open-source contributors looking to share edge-case scenarios or integrate new frameworks.

## Problem
Currently, when developers modify an agent (e.g., tweaking the system prompt, upgrading the model version, or adding new tools), they lack a deterministic way to understand the blast radius of their changes.
Traditional software relies on git diffs, unit tests, and CI/CD pipelines to catch regressions. AI agents, being highly stochastic, break these paradigms. Existing solutions are excellent for post-deployment tracing but offer terrible developer experiences for local, pre-commit regression testing.

## Positioning
AgentGuard is positioned as an open-source AI agent reliability and behavior engineering toolkit.
The mental model is: **"Git + pytest + OpenTelemetry for AI agent behavior."**

It is a workflow layer that lets developers treat AI agent behavior like software changes. Every agent run produces a reproducible artifact (the Agent Behavior Record).

## Non-Goals
AgentGuard is **NOT**:
- Another chatbot framework.
- Another tracing dashboard or SaaS platform.
- Another LLM evaluator or hosted enterprise management tool.
- A monolithic security scanner. (Security is just one community package: `agentguard-security`).

Whenever there is a choice between building more enterprise features or focusing on the open-source foundation, AgentGuard chooses the open-source foundation. Whenever choosing between automatic magic and transparent reproducibility, it chooses transparent reproducibility.
