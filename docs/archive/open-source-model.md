# Open Source Model

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Related:** `product-definition-v1.md`, `scenario-system.md`, `integration-strategy.md`, `security-package-migration.md`
**Does not replace:** `docs/open-source-strategy.md` (retained as the strategy trail).

---

## Thesis

AgentGuard grows the way **pytest** and **OpenTelemetry** grew: a small, boring, well-specified core that other people extend. The core team owns the **primitive** (`agent-record.json`), the **engine**, and the **plugin contract**. The community owns the **scenarios, adapters, and reporters**. Nothing valuable to a developer sits behind a login.

---

## Repository layout

```
agentguard/            # core — the primitive, engine, CLI, plugin API   (Apache-2.0)
community/             # community-owned, plugin-based extensions        (Apache-2.0)
├── scenarios/         #   reliability / security / quality / cost YAML sets
├── adapters/          #   L2/L3 framework integrations (openai, anthropic, langgraph, otel…)
├── reporters/         #   output formats (sarif, junit, html, slack, …)
└── examples/          #   reference agents (a "known-good" and "known-bad") + tutorials
```

- `agentguard` (core) is intentionally thin and dependency-light. It defines the record schema, the scenario schema, the check library, the diff/gate/report engines, and the **entry-point contracts** below.
- `community/` items are independently versioned plugins. They may live in-tree early, then graduate to their own repos once stable.

### License
**Apache-2.0** for core and community (permissive → maximum adoption and framework-author uptake; patent grant matters for an artifact aiming to be a standard). The optional commercial layer (Phase 5 governance/enterprise) is separately licensed and lives outside these repos.

---

## How plugins work

Three plugin types, each a Python entry point the core discovers at runtime:

| Type | Entry-point group | Contract | Example |
|---|---|---|---|
| **Scenario set** | `agentguard.scenarios` | Directory of YAML validated against the scenario schema | `agentguard-security` ships the ASI scenarios |
| **Adapter** | `agentguard.adapters` | `record(...) -> AgentRecord` producer for a framework/SDK/source | `agentguard-openai`, `agentguard-otel` |
| **Reporter** | `agentguard.reporters` | `render(record | diff) -> bytes/str`, pure, no mutation | `agentguard-slack` |

```toml
# a plugin's pyproject.toml
[project.entry-points."agentguard.scenarios"]
security = "agentguard_security.scenarios"

[project.entry-points."agentguard.reporters"]
junit = "agentguard_junit:render"
```

`pip install agentguard-security` and its scenarios appear in `agentguard test` automatically. This is the pytest model exactly: install a plugin, it registers itself, no config edit required.

---

## How contributors participate

1. **Add a scenario** (lowest barrier): open a PR to `community/scenarios/<category>/`. CI validates schema + runs it against the reference known-good / known-bad agents. A scenario that doesn't *discriminate* (passes on the bad agent or fails on the good one) is rejected. This keeps quality high without gatekeeping taste.
2. **Add an adapter/reporter:** new `pip`-installable plugin implementing the entry-point contract, with a conformance test.
3. **Improve the core:** engine/checks/format changes go through the ADR + adversarial-review gate (core is the stable surface; changes here are slower by design).

Governance: core-team-owned merge rights on `agentguard/`; a lighter reviewer pool for `community/`. Contribution ladder: scenario author → adapter author → community maintainer → core.

---

## How compatibility is maintained

**Every artifact carries three versions — this is the compatibility backbone:**

| Version | On the… | Guarantees |
|---|---|---|
| `schema_version` | record | Format stability (SemVer; MAJOR = breaking, readers reject unknown MAJOR, tolerate unknown fields) |
| `scenario_version` (+ `scenario_lib_version`) | scenario / evaluation | A verdict is reproducible against a known scenario snapshot |
| `engine_version` | evaluation | Which engine produced the proofs |

Rules:
- A plugin declares the minimum `engine_version` and `schema_version` MAJOR it supports.
- Core promises: no breaking `schema_version` change without a MAJOR bump and a one-MAJOR deprecation window.
- Forward-compat is mandatory: consumers ignore unknown fields; `fingerprint.algo` and `signature.scheme` are named so identity/signing can evolve *without* a format break.
- A **conformance suite** (fixture records + expected verdicts) is published with core; any adapter/reporter/scenario set is "AgentGuard-compatible" iff it passes the suite. This is how a third-party framework author can claim compatibility without our involvement — the definition of a standard.

---

## Why this drives community growth

- **Four contribution surfaces, all low-friction:** scenarios (YAML PRs), adapters, reporters, examples. Someone can add value in an hour.
- **Install-to-activate plugins** (pytest model): no config, so the marginal cost of a new plugin to a user is near zero — plugins actually get used.
- **The reference known-good/known-bad agents** give every scenario an objective bar, so the library stays trustworthy as it scales.
- **Compatibility is mechanical, not social:** the conformance suite + version triple let the ecosystem expand without the core team as a bottleneck.

See `implementation-roadmap-v2.md` for when each surface opens (community ecosystem is Phase 4; security package is Phase 5).
