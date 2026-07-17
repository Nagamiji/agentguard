"""Customer-facing scan reports — the first thing a person actually understands.

`agentguard scan --html report.html` renders a verdict the way the mock does: agent, model,
fingerprint, policy status, the decision, each finding with its evidence, and a concrete
remediation. The HTML is fully self-contained (inline CSS, no external requests), so it opens
offline and can be attached to a PR or a ticket.

Everything dynamic is HTML-escaped: a finding detail can contain arbitrary agent output, and a
report that rendered it raw would be an injection vector in the very tool meant to catch them.
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from typing import Any

# check_type -> concrete remediation. The report is only useful if it tells an engineer what
# to DO, not just what failed.
RECOMMENDATIONS: dict[str, str] = {
    "tool_arg_limit": (
        "The agent passed a tool argument beyond the allowed limit. Tighten the policy "
        "ceiling, and have the agent validate or clamp the value before calling the tool."
    ),
    "must_not_call_tool": (
        "The agent called a forbidden tool. Remove it from the agent's manifest, or keep it "
        "in the policy's forbidden_tools list."
    ),
    "must_not_use_tools": (
        "The agent took action on a request that needed none — a sign it followed injected "
        "instructions. Harden the system prompt to treat user content as data, not commands, "
        "and reduce the tool permissions available on low-trust requests."
    ),
    "must_not_output": (
        "The agent revealed content it should not. Add output filtering and instruct the "
        "agent never to disclose internal data, secrets, or its system prompt."
    ),
    "max_tool_calls": (
        "The agent exceeded the allowed number of tool calls. Reduce its autonomy or lower "
        "the policy limit."
    ),
    "must_call_tool": "The agent skipped a required step. Verify the prompt and tools support it.",
    "must_output": "The agent omitted required output. Verify the prompt elicits it.",
    "policy_allowed_providers": (
        "The agent uses a model provider the policy disallows. Switch to an approved provider "
        "or update the policy's allowed_providers."
    ),
    "policy_allowed_model_families": (
        "The agent uses a model family the policy disallows. Switch to an approved model or "
        "update allowed_model_families."
    ),
    "policy_forbidden_tool_declared": (
        "The agent declares a tool the policy forbids. Remove the tool from the manifest."
    ),
    "policy_tool_not_allowed": (
        "The agent declares a tool that is not on the policy's allow-list. Remove it or add it "
        "to allowed_tools."
    ),
}

_FALLBACK = "Review the finding and align the agent's configuration or the governing policy."


def recommend(check_type: str) -> str:
    return RECOMMENDATIONS.get(check_type, _FALLBACK)


def build_report(
    *,
    agent_name: str,
    manifest: dict[str, Any] | None,
    effective_policy: dict[str, Any] | None,
    gate: dict[str, Any],
    risk: dict[str, Any],
    environment: str | None,
) -> dict[str, Any]:
    """A structured, self-describing report from the verdict + context."""
    model = ""
    if manifest and isinstance(manifest.get("model"), dict):
        model = str(manifest["model"].get("id", ""))

    policy_rules = []
    if effective_policy:
        for rule, spec in (effective_policy.get("effective") or {}).items():
            policy_rules.append(
                {"rule": rule, "value": spec.get("value"), "source": spec.get("source")}
            )

    findings = [
        {
            "check_type": f.get("check_type"),
            "severity": f.get("severity"),
            "category": f.get("category"),
            "detail": f.get("detail"),
            "recommendation": recommend(str(f.get("check_type", ""))),
        }
        for f in (gate.get("failures") or [])
    ]

    return {
        "agent": agent_name,
        "model": model,
        "fingerprint": gate.get("fingerprint", ""),
        "environment": environment,
        "decision": gate.get("decision", "unknown"),
        "risk_level": risk.get("risk_level", ""),
        "reason": gate.get("reason", ""),
        "generated_at": datetime.now(UTC).isoformat(),
        "signature": gate.get("signature"),
        "policy": policy_rules,
        "deferred_runtime_rules": (effective_policy or {}).get("deferred_runtime") or [],
        "findings": findings,
    }


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)


_BADGE = {
    "blocked": ("#b91c1c", "🔴 BLOCKED"),
    "allowed": ("#15803d", "🟢 ALLOWED"),
    "unknown": ("#a16207", "🟡 UNKNOWN"),
}


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


_CSS = """
  :root { color-scheme: light dark; }
  body { font: 15px/1.5 -apple-system, system-ui, sans-serif; max-width: 760px;
         margin: 2rem auto; padding: 0 1rem; color: #111; }
  @media (prefers-color-scheme: dark) {
    body { color: #e5e5e5; background: #111; }
    code { color: #ddd; }
  }
  h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
  .meta { color: #666; font-size: .9rem; margin-bottom: 1.25rem; }
  .badge { display:inline-block; padding:.35rem .8rem; border-radius:6px;
           color:#fff; font-weight:700; background: var(--accent); }
  .card { border:1px solid #ccc3; border-radius:8px; padding:1rem 1.2rem; margin:1rem 0; }
  h2 { font-size: 1rem; text-transform: uppercase; letter-spacing:.04em;
       color:#888; margin:.2rem 0 .6rem; }
  ul { margin:.3rem 0; padding-left:1.2rem; }
  code { background:#8881; padding:.05rem .3rem; border-radius:3px; }
  .src { color:#888; font-size:.85rem; }
  .muted { color:#888; }
  .finding { border-left:4px solid var(--accent); padding:.5rem .8rem;
             margin:.6rem 0; background:#8881; border-radius:4px; }
  .finding .sev { text-transform:uppercase; font-weight:700; font-size:.8rem; margin-right:.5rem; }
  .evidence, .rec { margin-top:.3rem; }
"""


def render_html(report: dict[str, Any]) -> str:
    """A self-contained HTML report (no external requests)."""
    color, badge = _BADGE.get(str(report["decision"]), ("#a16207", str(report["decision"]).upper()))

    policy_rows = (
        "".join(
            f"<li><code>{_e(p['rule'])}</code> = {_e(p['value'])} "
            f"<span class='src'>(from {_e(p['source'])})</span></li>"
            for p in report["policy"]
        )
        or "<li class='muted'>No policy in effect.</li>"
    )

    if report["findings"]:
        finding_cards = "".join(
            f"""<div class="finding sev-{_e(f["severity"])}">
              <div class="fhead"><span class="sev">{_e(f["severity"])}</span>
                <code>{_e(f["check_type"])}</code></div>
              <div class="evidence"><strong>Evidence:</strong> {_e(f["detail"])}</div>
              <div class="rec"><strong>Recommendation:</strong> {_e(f["recommendation"])}</div>
            </div>"""
            for f in report["findings"]
        )
    else:
        finding_cards = "<p class='muted'>No findings.</p>"

    deferred = ""
    if report["deferred_runtime_rules"]:
        deferred = (
            "<p class='muted'>Runtime-only policy rules (declared, enforced at runtime not "
            f"deploy time): {_e(', '.join(report['deferred_runtime_rules']))}</p>"
        )

    sig = (
        f"<p class='muted'>Signed verdict: <code>{_e(report['signature'])[:24]}…</code></p>"
        if report["signature"]
        else ""
    )

    risk = _e(report["risk_level"]) or "n/a"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentGuard report — {_e(report["agent"])}</title>
<style>{_CSS}</style></head><body style="--accent:{color}">
  <h1>{_e(report["agent"])}</h1>
  <div class="meta">
    Model: <code>{_e(report["model"]) or "—"}</code> &nbsp;·&nbsp;
    Fingerprint: <code>{_e(report["fingerprint"])[:12]}…</code> &nbsp;·&nbsp;
    Environment: {_e(report["environment"]) or "default"}<br>
    Generated {_e(report["generated_at"])}
  </div>

  <p><span class="badge">{_e(badge)}</span>
     &nbsp; risk: <strong>{risk}</strong></p>
  <p>{_e(report["reason"])}</p>

  <div class="card"><h2>Policy</h2><ul>{policy_rows}</ul>{deferred}</div>
  <div class="card"><h2>Findings</h2>{finding_cards}</div>
  {sig}
  <p class="muted">Generated by AgentGuard. Evidence is from a simulated evaluation —
  the agent's real tools were never executed.</p>
</body></html>"""
