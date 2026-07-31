# Open Source Strategy

## Contributor Model
AgentGuard is designed for community contribution from day one. The core is kept small, while extensibility is prioritized. By defining a strict primitive—the Agent Behavior Record (snapshot)—we enable contributors to build around it without needing deep knowledge of the core engine.

## Ecosystem
The ecosystem is driven by two main growth loops:
1. **Scenario sharing**: Companies and researchers sharing failure cases.
2. **Framework adapters**: Developers writing adapters to export their framework's execution traces to the Agent Behavior Record format.

Every artifact in the ecosystem (snapshot, scenario, plugin) must be versioned with:
- `schema_version`
- `scenario_version`
- `engine_version`

## Plugins
A lightweight plugin model will allow developers to contribute:
- **Adapters**: Connectors for various LLM frameworks (OpenAI SDK, LangChain, Anthropic, custom wrappers).
- **Reporters**: Custom CLI outputs (e.g., markdown reports, custom CI integrations).
- **Evaluators**: Custom assertion logic for specific domains.

## Scenarios (Marketplace)
The scenario system is community-friendly, defined in declarative YAML files. A community marketplace structure will look like:

```text
community/
  scenarios/
    security/
      prompt-injection.yaml
    reliability/
      hallucinations.yaml
    customer-support/
      refund-approval.yaml
    coding-agent/
      file-overwrite.yaml
```

This structure makes it easy for developers to pull in high-quality, pre-built test cases for their specific domain, driving initial adoption.
