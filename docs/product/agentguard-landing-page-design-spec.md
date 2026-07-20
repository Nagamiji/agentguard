# AgentGuard Landing Page — Design System & Experience Specification

**Status:** DESIGN SPEC — no frontend code. Awaiting founder approval before wireframe → build.
**Author:** Product Designer + Frontend Architect (Claude), from the approved Gemini visual research.
**Discipline:** decide the experience first, build second — the same gate we used for security work.

**Grounding rule (non-negotiable): every terminal block, policy snippet, CI workflow, exit code,
and screenshot in this spec maps to something the product *actually does today*.** The commands,
outputs, and files below are taken from the real CLI (`cli/src/agentguard_cli/`), the composite
Action (`.github/actions/agentguard/`), and the self-contained HTML report (`report.py`). No
invented UI. The single biggest "avoid fake features" call is in §5: **AgentGuard deliberately has
no dashboard** (`CLAUDE.md`, `adr-0014`), so the site must never show one.

---

## 1. Final positioning

**One line (hero):** *A declarative, fail-closed CI/CD deploy gate for AI agents.*

**Expanded:** AgentGuard evaluates an AI agent's configuration against policy-as-code **before it
ships**, in CI, and **blocks the deploy** when the agent would take an unsafe action — deterministically,
reproducibly, and without ever executing the agent's tools.

**The three proof-points the whole page must earn (in priority order):**
1. **It blocks.** The product's job is a red gate in CI. The hero shows a real `BLOCKED`.
2. **It's deterministic & fail-closed.** Not an LLM judging an LLM. Same input → same verdict; "we
   couldn't tell" → blocked, never "looks fine."
3. **It's developer-native.** A CLI whose **exit code is the CI contract**, policy-as-code in the
   repo, findings in the PR (SARIF). No console to log into.

**Voice:** infrastructure, not intelligence. We describe *guarantees* (fail-closed, deterministic,
simulate-never-execute, reproducible verdicts keyed to a fingerprint), not *capabilities of a model*.

**Positioning guardrails (from research — enforce in copy and art):**
| Say | Never imply |
|---|---|
| deploy gate · policy engine · CI check · trust infrastructure | AI chatbot / assistant |
| deterministic checks · fail-closed · simulate-never-execute | "our AI decides" / LLM-as-judge |
| security & reliability for agents you build | a generic "AI platform" |
| boring, auditable, reproducible | a futuristic AI experiment |

---

## 2. Target audience

### Primary (must convert self-serve; the page is built for them)
| Persona | What they need to see | What convinces them | CTA that works |
|---|---|---|---|
| **AI / agent engineers** | that it drops into an existing agent + CI without rework | a real terminal `BLOCKED`, copy-paste `pip install`, the exit-code contract | `pip install agentguard-dev` → `agentguard init` |
| **Platform / DevEx engineers** | the GitHub Action, policy-as-code, SARIF in the PR | the generated workflow file + findings in the PR's Code-Scanning tab | "Add the GitHub Action" |
| **Security engineers** | the guarantees: fail-closed, deterministic, simulate-never-execute, tenant isolation | the security-architecture section + signed verdicts (HMAC) | "Read the security architecture" |

### Secondary (must not bounce; give them the story + trust)
| Persona | What they need | Convinces them | CTA |
|---|---|---|---|
| **Eng managers** | the risk in one sentence + that it's low-lift | the Problem section (the $9,000 refund) + "one CI check" | "See how it works" (scroll) |
| **Enterprise buyers** | audit trail, reproducibility, isolation, RBAC | Audit & Trust section + Security architecture | "Talk to engineering" (technical walkthrough, not a sales demo) |

**Design consequence:** the page is **code-forward** for the primary audience, with a **legible
narrative spine** (problem → how → proof) so a manager scrolling without reading code still gets it.

---

## 3. Page structure (information architecture)

Ten sections. Each: purpose · the user question it answers · primary visual · animation · priority
(P0 = launch-blocking, P1 = launch-ideal, P2 = fast-follow). "Real" vs "mock" is defined in §5.

| # | Section | User question | Purpose | Primary visual | Animation | Priority |
|---|---|---|---|---|---|---|
| 1 | **Hero** | "What is this?" | State the gate + show it block, in 5 seconds | **TerminalWindow** running `agentguard scan` → `BLOCKED` + **VerdictBadge** (real output) | Terminal type-out (once) → verdict snaps to red | **P0** |
| 2 | **Problem** | "Why do I need it?" | The tool call is the danger; text scorers miss it | Split: a fluent "Certainly! I've processed the $9,000 refund" vs the **tool call** that did it | Reveal the tool call under the prose | **P0** |
| 3 | **How it works** | "What does it actually do?" | 4 honest steps: manifest → compile policy → simulate + deterministic checks → gate | **PipelineRail** (4 nodes) | Sequential node activation on scroll | **P0** |
| 4 | **Developer workflow** | "How do I use it?" | `install → init → scan`; exit code is the contract | **CodeTabs** (CLI) + **ExitCodeTable** | Tab switch; row highlight | **P0** |
| 5 | **Policy-as-code** | "How do I express rules?" | Real `policy.json` compiles to checks; provenance | **PolicyCodeBlock** (real `max_tool_arg`) → **SecurityCheckRow** | Rule line → derived check (draw connector) | **P0** |
| 6 | **CI/CD integration** | "Does it fit my pipeline?" | The generated Action; findings land in the PR | **IntegrationCard**s + **SARIF-in-PR** screenshot (real GitHub UI) | Static / subtle hover | **P0** |
| 7 | **Security architecture** | "Why trust the verdict?" | Simulate-never-execute, deterministic, fail-closed, isolation, signed | **ArchitectureDiagram** + **PropertyChip** row | Chips settle in; diagram draws on scroll | **P1** |
| 8 | **Audit & trust** | "Can I prove what happened?" | Reproducible verdicts keyed to fingerprint; audit trail; the **HTML report** | **Report** embed (real `--html` output) + **TrustBadge**s | Report fades in; no fake console | **P1** |
| 9 | **Ecosystem / roadmap (A2A, MCP)** | "Where is this going?" | Honest forward-look; clearly labeled roadmap | Minimal roadmap rail | None / minimal | **P2** |
| 10 | **CTA** | "How do I start?" | Self-serve first, talk-to-us second | Install command + two buttons | Copy-to-clipboard tick | **P0** |

**Scroll spine (what a non-reader absorbs from headlines alone):** *AI agents can take unsafe actions
→ AgentGuard checks the action, not the words → in CI, before deploy → deterministically → and blocks
it → here's the one command.*

**Nav:** minimal top bar — wordmark · How it works · Docs · GitHub · `pip install` (primary). Sticky,
translucent over `--bg`. No mega-menu.

---

## 4. Hero decision

**Recommendation: Option C — Hybrid, terminal-led.** Reject pure A (opaque to managers/buyers) and
pure B (a generic box-and-arrow diagram doesn't convey the product's actual *behavior*, and it's the
most-copied AI-infra cliché). The hybrid keeps developer credibility as the anchor while making the
outcome legible to everyone.

**Composition (desktop, two-column):**
- **Left:** headline + subhead + primary CTA (`pip install agentguard-dev`) + secondary ("How it works").
- **Right:** a **TerminalWindow** that types the real command and resolves to the real output, with a
  compact **VerdictBadge** and a 4-dot **PipelineRail** beneath it (the architecture, miniaturized —
  so B's clarity is present without a separate generic diagram).

The terminal content is **verbatim from the CLI** (`Outcome.render()`), using the **BLOCKED** case —
the money shot ("it caught a $9,000 refund the model was happy to issue"):

```
$ agentguard scan --agent customer-support-bot --manifest manifest.json --environment prod

AgentGuard
  decision:    BLOCKED
  risk:        high
  fingerprint: 3f9a…c21b
  reason:      policy violation: issue_refund.amount exceeds max_tool_arg ($100)
  [HIGH] tool_arg_limit: issue_refund called with amount=9000, limit=100

$ echo $?
20
```

- The trailing `echo $?` → `20` makes the **exit-code-is-the-contract** claim in the first screen.
- **Mobile:** single column, headline first, terminal below at full width, horizontal-scroll-safe;
  the type-out still runs once, then rests.
- **Accessibility:** the terminal is real text (selectable, not an image), with the type-out purely
  cosmetic; the final state is present immediately for `prefers-reduced-motion` and screen readers.

Headline options to A/B (all avoid "AI-magic" framing):
1. **"Block unsafe AI agents before they ship."** (action-first — recommended)
2. "A fail-closed deploy gate for AI agents."
3. "Your agent passed the vibe check. Did it pass the policy?"

---

## 5. Product screenshots & demos — real vs. mock (avoid fake features)

This is the section that keeps us honest. The truth of the product constrains the art.

### Show as REAL (authentic, product-accurate)
| Asset | Why it's real | Source of truth |
|---|---|---|
| **CLI terminal output** | It *is* the product surface | `Outcome.render()`, exit codes `commands.py` |
| **Exit-code contract** | `0 allowed · 10 error · 20 blocked · 30 unknown` | `commands.py` (`EXIT_*`) |
| **Policy / manifest files** | `agentguard init` writes these exact files | `commands.py` templates |
| **Generated GitHub workflow** | `init` writes `.github/workflows/agentguard.yml` | `commands.py` |
| **SARIF findings in the PR** | We emit SARIF 2.1.0; GitHub renders it in Code-Scanning | `sarif.py`, composite Action |
| **Self-contained HTML report** | `agentguard scan --html` renders it today | `report.py` (`adr-0014`) |

### Show as MOCK (clearly conceptual — a diagram, never a "screenshot")
| Asset | Framing |
|---|---|
| **PipelineRail** (manifest → compile → simulate → gate) | An illustrative flow, styled as a diagram, not chrome pretending to be a UI |
| **ArchitectureDiagram** (control plane + workers, tenant isolation) | Conceptual system diagram |

### DO NOT build or depict — these would be fake features
- **A web dashboard / admin console.** The product **deliberately has none** (`CLAUDE.md`: "A dashboard
  is deliberately not built"; `adr-0014`: "the report is the minimal visualization"). A hero or
  screenshot showing a dashboard would misrepresent the product and undercut the "boring, honest
  infrastructure" positioning.
- **A web-based policy editor GUI.** Policy is code in the repo (`policy.json`), enforced in CI. Show
  the file, not an editor.
- **A web audit-log viewer / SIEM console.** The audit trail is API/CLI-accessible and appears in the
  HTML report; there is no web console. §8 uses the **real report**, not a fabricated log UI.
- Any metric/graph "dashboard" implying a hosted analytics product.

> If we later want a screenshot with more visual surface than a terminal, the **HTML report is the
> only sanctioned "UI" asset**, because it exists. Everything richer is a diagram, explicitly styled
> as one.

---

## 6. Visual system

### 6.1 Color

Dark-first (the developer default). Green and red are **load-bearing semantic tokens** — they mean
*allowed* and *blocked*. **Rule: never use success-green or danger-red decoratively** (no green
gradient washes, no red glow for style). Keeping the traffic-light meaning uncorrupted *is* the
fail-closed brand.

**Surfaces & structure**
| Token | Value | Use |
|---|---|---|
| `--bg` | `#0B0F19` | page base (approved) |
| `--surface-1` | `#0F1420` | cards, terminal body |
| `--surface-2` | `#141B2B` | elevated / hover |
| `--border` | `#1E2637` | hairline dividers, card edges |
| `--border-strong` | `#2A3550` | focused/active edges |

**Text hierarchy**
| Token | Value | Use |
|---|---|---|
| `--text-hi` | `#E8ECF4` | headings, primary |
| `--text` | `#B7C0D0` | body |
| `--text-mut` | `#7A8699` | captions, secondary |
| `--text-faint` | `#55607A` | disabled, watermarks |

**Brand & semantic**
| Token | Value | Use |
|---|---|---|
| `--brand` | `#5B8CFF` | primary accent, links, primary CTA (calm "signal blue" — security credibility, not playful) |
| `--brand-ink` | `#0B0F19` | text on `--brand` |
| `--success` | `#10B981` | verdict **allowed** only (approved) |
| `--danger` | `#EF4444` | verdict **blocked** / violations only (approved) |
| `--warn` | `#F59E0B` | **unknown** / degraded / fail-closed-caution |
| `--info` | `#38BDF8` | neutral callouts, "deferred/runtime-declared" policy notes |

**Code syntax palette** (restrained, dark): keys `#8AB4FF`, strings `#7EE0B8`, numbers `#F0B072`,
punctuation `--text-mut`, comments `#55607A`. The violation value in a code block may use `--danger`
— that's semantic, not decorative.

**Light mode:** P1. Provide a mapped light palette (bg `#FFFFFF`, surface `#F6F8FB`, borders
`#E4E9F2`, text `#0B0F19` / secondary `#475069`), same semantic greens/reds. Theme-toggle persists.

### 6.2 Typography

Three families, all open-source / proven (matches "boring, proven tech"):
| Role | Font | Fallback | Notes |
|---|---|---|---|
| Display / headings | **Geist** (or Inter) | system-ui | tight tracking on large sizes; Vercel-DX feel |
| Body / UI | **Inter** | system-ui | 400/500/600 |
| Code / terminal | **Geist Mono** (or JetBrains Mono) | ui-monospace, SFMono | the terminal & all code blocks — *same mono a dev's editor uses*, for authenticity |

**Type scale** (rem, ~1.2 ratio): 0.75 · 0.875 · 1 · 1.125 · 1.25 · 1.5 · 1.875 · 2.25 · 3 · 3.75.
- Hero H1 `clamp(2.25rem, 5vw, 3.75rem)`, line-height 1.05, tracking `-0.02em`.
- Section H2 `1.875–2.25rem`, 1.15, `-0.01em`. Body `1rem–1.125rem`, 1.6. Code `0.875rem`, 1.5.

**Spacing:** 4px base; scale 4/8/12/16/24/32/48/64/96/128. Section vertical rhythm 96–128px desktop,
64px mobile. Max content width 1120px; prose measure ≤ 68ch.

**Radius & elevation:** radius 8 (controls) / 12 (cards) / 16 (terminal). Elevation via border +
subtle shadow (`0 1px 0 rgba(255,255,255,.03)` inset, `0 8px 30px rgba(0,0,0,.35)`), **not** glow.

---

## 7. Animation rules

**Principles:** motion explains state (a verdict flips, a pipeline advances), never decorates.
Everything respects `prefers-reduced-motion` (→ show final state, no motion). No autoplaying infinite
loops, no parallax, no layout shift, nothing that delays content or interaction. Budget: ≤ a handful
of small animations per view; 60fps; transform/opacity only.

### Allowed
| Animation | Purpose | Difficulty | Perf |
|---|---|---|---|
| **Terminal type-out** (hero, once) | show the product running | Low (CSS steps / tiny JS) | Negligible (text) |
| **Verdict snap** allowed→blocked (color+icon) | make the block *felt* | Low (CSS transition) | Negligible |
| **PipelineRail sequential activation** (on scroll) | convey the 4 honest steps | Med (IntersectionObserver) | Low |
| **Policy → check connector draw** (§5) | show a rule compiling into a check | Med (SVG stroke-dashoffset) | Low |
| **Scroll-reveal** (fade/translate ≤ 8px, once) | pacing | Low | Low |
| **Hover micro-states** (cards, buttons, copy-tick) | affordance/feedback | Low | Negligible |

### Forbidden (from research — hard no)
AI "brains" / neural art · floating particles · WebGL / shader backgrounds · spinning or drifting 3D
objects · animated gradient meshes · parallax hero · anything that loops forever or moves while the
user reads. **Reason:** they signal "AI experiment," the exact positioning we reject, and they cost
performance and credibility.

---

## 8. Component list (implementation-ready inventory)

Framework-agnostic contracts (props/states), so wireframe and build inherit one vocabulary. All are
static/CSS-driven unless noted; all theme-aware; all keyboard/AXE-clean.

| Component | Purpose | Key props | States / notes | Data |
|---|---|---|---|---|
| **TerminalWindow** | render a real CLI session | `command`, `output`, `exitCode`, `typing?` | typing → settled; selectable text; mono | REAL |
| **VerdictBadge** | the decision pill | `decision` (allowed/blocked/unknown/error) | maps to success/danger/warn; icon + label | REAL |
| **PipelineRail** | 4-step honest flow | `steps[]`, `activeIndex` | scroll-activated; horizontal desktop / vertical mobile | MOCK (diagram) |
| **PolicyCodeBlock** | policy/manifest as code | `lang`, `code`, `highlightLines?`, `annotations?` | copy button; provenance annotation gutter | REAL |
| **SecurityCheckRow** | a compiled check / finding line | `severity`, `checkType`, `detail` | severity color chip; used in report + §5 | REAL |
| **FindingCard** | a violation + remediation | `severity`, `title`, `evidence`, `remediation` | expandable; danger accent | REAL (report shape) |
| **ExitCodeTable** | the CI contract | rows of `code`, `meaning` | highlight `20`/`30` (fail-closed) | REAL |
| **PipelineVisualizer** | animated scan run (§3 detail) | `stage`, `result` | reduced-motion → static | MOCK (diagram) |
| **ArchitectureDiagram** | system/trust boundaries | `nodes`, `edges` | SVG; draws on scroll | MOCK (diagram) |
| **PropertyChip / TrustBadge** | a guarantee | `label`, `icon`, `tone` | fail-closed · deterministic · simulate-never-execute · HMAC-signed · tenant-isolated | REAL claims |
| **IntegrationCard** | GitHub Action / CLI / SARIF | `icon`, `title`, `blurb`, `href` | hover lift (border, not glow) | REAL |
| **CodeTabs** | switch CLI/CI/policy views | `tabs[]` | keyboard-navigable tablist | REAL |
| **SarifInPRImage** | findings in the PR | responsive `<img>` w/ real screenshot | `max-width:100%`; alt text | REAL (GitHub UI) |
| **Callout** | notes / roadmap flags | `tone` (info/warn), `children` | used to mark §9 as roadmap | — |
| **CTAButton / CopyCommand** | convert | `variant`, `command` | copy-to-clipboard tick | REAL |
| **SectionHeader** | consistent section intros | `eyebrow`, `title`, `sub` | — | — |

---

## 9. Implementation phases

**Phase 1 — Launch (P0 sections, static-first).** Hero (TerminalWindow + VerdictBadge), Problem, How
it works (PipelineRail), Developer workflow (CodeTabs + ExitCodeTable), Policy-as-code
(PolicyCodeBlock + SecurityCheckRow), CI/CD (IntegrationCard + real SARIF-in-PR image), CTA. Dark
theme only. Allowed animations limited to: terminal type-out, verdict snap, scroll-reveal, hover.
Design system tokens + the component contracts above. **This is a shippable, honest landing page.**

**Phase 2 — Depth (P1).** Security architecture (ArchitectureDiagram + PropertyChips), Audit & trust
(embed/screenshot the **real HTML report**), light mode, pipeline connector-draw animation, polish
pass on motion.

**Phase 3 — Fast-follow (P2).** Ecosystem/roadmap (A2A, MCP) as clearly-labeled roadmap, an
interactive "try a policy → see the check it compiles to" toy (still simulate-only, no fake backend),
docs cross-links, per-persona secondary CTAs.

**Tech direction for the build stage (decide at wireframe sign-off, not now):** static-site or
React/Next with all content server-rendered; **no client-side 3D/WebGL**; ship system-fonts-first with
the three families self-hosted; images as responsive assets; Lighthouse ≥ 95 perf/a11y as a gate.
Self-contained, CSP-clean (mirrors the report's own discipline).

---

## 10. Things explicitly avoided

- **A dashboard, policy-editor GUI, or web audit console** — the product has none; depicting one is a
  fake feature (§5). The HTML report is the only sanctioned rich "UI" asset.
- **"AI-magic" art** — brains, particles, WebGL, floating 3D, animated gradient meshes, parallax.
- **LLM-as-judge framing** — we never imply a model decides; checks are deterministic assertions.
- **Chatbot/assistant/"AI platform" positioning** — we are a deploy gate / trust infrastructure.
- **Decorative use of success-green / danger-red** — reserved for verdict semantics.
- **Invented metrics, logos, testimonials, or customer counts** — no fabricated social proof.
- **Motion that loops, delays content, or shifts layout** — and nothing that ignores reduced-motion.
- **Overclaiming the roadmap** — A2A/MCP shown as roadmap, not shipped.

---

## Appendix A — Real assets to capture for the build (no invention required)
1. Terminal recordings/text for **BLOCKED** (hero) and **allowed** (§4) from `agentguard scan`.
2. The three `init`-generated files: `manifest.json`, `policy.json`, `.github/workflows/agentguard.yml`.
3. A **SARIF-in-PR** screenshot (GitHub Code-Scanning tab) from a real scan.
4. A rendered **HTML report** (`agentguard scan --html report.html`) for §8.
5. The exit-code table `0/10/20/30` and the `--fail-on {blocked,unknown,any}` default (`unknown`).

## Appendix B — Copy seeds (positioning-safe)
- Hero sub: "AgentGuard compiles your policy, simulates your agent's tool calls, and fails the build
  when it would do something it shouldn't — deterministically, before it ships."
- Problem: "'Certainly — I've processed the $9,000 refund' reads great. The refund is the problem.
  AgentGuard judges the **action**, not the prose."
- Trust: "If we can't tell, we block. Unknown is not 'fine'."

---

**Next founder decision:** approve this spec → commission the **wireframe/prototype** → then frontend
implementation. No React/Tailwind until the wireframe is signed off.
