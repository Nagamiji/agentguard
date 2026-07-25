"""`agentguard` entry point: parse args, call the API, print, and exit with the CI code.

AgentGuard is a pre-deployment security verification layer for AI agents.
It simulates adversarial scenarios against your agent's configuration and blocks unsafe
releases before they reach production — without executing real tools or accessing secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from agentguard_cli import __version__
from agentguard_cli.api import ApiClient
from agentguard_cli.commands import (
    Outcome,
    do_fingerprint,
    do_policy_check,
    do_report,
    do_scan,
)

_DEFAULT_URL = os.getenv("AGENTGUARD_API_URL", "http://localhost:8000")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentguard", description="AgentGuard deployment gate")
    parser.add_argument("--version", action="version", version=f"agentguard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_api_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--api-url", default=_DEFAULT_URL, help="AgentGuard API base URL")
        p.add_argument(
            "--api-key",
            default=os.getenv("AGENTGUARD_API_KEY", ""),
            help="API key (or set AGENTGUARD_API_KEY)",
        )
        p.add_argument(
            "--agent",
            default=None,
            help="agent id or slug (required for cloud mode, optional for --local)",
        )
        p.add_argument("--environment", default=None, help="dev/staging/prod")
        p.add_argument("--sarif", default=None, help="write SARIF findings to this path")
        p.add_argument("--html", default=None, help="write a self-contained HTML report")
        p.add_argument("--report-json", default=None, help="write the structured JSON report")
        p.add_argument("--json", action="store_true", help="print the verdict as JSON")
        p.add_argument(
            "--fail-on",
            choices=["blocked", "unknown", "any"],
            default="unknown",
            help="which verdicts exit non-zero (default: unknown = block + unknown)",
        )

    fp = sub.add_parser("fingerprint", help="compute a manifest's fingerprint locally")
    fp.add_argument("manifest", help="path to the agent manifest JSON")

    for name in ("scan", "evaluate"):
        s = sub.add_parser(name, help="evaluate an agent version and gate the deploy")
        add_api_args(s)
        s.add_argument(
            "--manifest",
            default=None,
            help=(
                "path to the agent manifest (JSON or YAML). "
                "Defaults to agentguard.yaml then manifest.json"
            ),
        )
        s.add_argument("--runner", default="scripted", help="evaluation runner (scripted|vertex)")
        s.add_argument(
            "--import-library",
            action="store_true",
            help="seed the built-in attack library before scanning",
        )
        s.add_argument(
            "--local",
            action="store_true",
            help="run evaluation locally without any cloud dependency (no API key required)",
        )
        s.add_argument(
            "--allow-incomplete-static",
            action="store_true",
            help=(
                "accept a PARTIAL gate: exit 0 even when behavioural scenarios were skipped "
                "because STATIC CHECK cannot run them (otherwise such a run exits 40)"
            ),
        )

    rep = sub.add_parser("report", help="report the verdict for an already-evaluated fingerprint")
    add_api_args(rep)
    rep.add_argument("--fingerprint", required=True)

    pol = sub.add_parser("policy", help="policy commands")
    pol_sub = pol.add_subparsers(dest="policy_command", required=True)
    check = pol_sub.add_parser("check", help="static policy pre-check for an agent")
    check.add_argument("--api-url", default=_DEFAULT_URL)
    check.add_argument("--api-key", default=os.getenv("AGENTGUARD_API_KEY", ""))
    check.add_argument("--agent", required=True)
    check.add_argument("--environment", default=None)
    check.add_argument("--json", action="store_true")

    init = sub.add_parser("init", help="initialize configuration templates for AgentGuard")
    init.add_argument("--dir", default=".", help="directory to write templates to (default: .)")

    return parser


def _client(args: argparse.Namespace) -> tuple[ApiClient, Any]:
    import httpx

    http = httpx.Client(base_url=args.api_url, timeout=120.0)
    return ApiClient(http, args.api_key), http


_MANIFEST_SEARCH_ORDER = ("agentguard.yaml", "agentguard.yml", "manifest.json")


def _load_manifest(manifest_arg: str | None) -> tuple[dict[str, Any], str]:
    """Load a manifest from the given path, or search for one in the current directory.

    Returns (manifest_dict, resolved_path_string).
    Supports JSON and YAML (if pyyaml is available).
    """
    if manifest_arg is not None:
        return _parse_manifest_file(Path(manifest_arg)), manifest_arg

    # Auto-discover: prefer agentguard.yaml, fall back to manifest.json
    for name in _MANIFEST_SEARCH_ORDER:
        candidate = Path(name)
        if candidate.exists():
            return _parse_manifest_file(candidate), str(candidate)

    print(
        "Could not find agentguard.yaml or manifest.json in the current directory.\n"
        "Run `agentguard init` to create one.",
        file=sys.stderr,
    )
    sys.exit(10)


def _parse_manifest_file(path: Path) -> dict[str, Any]:
    """Parse a manifest file. Supports JSON and YAML."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read manifest: {exc}", file=sys.stderr)
        sys.exit(10)

    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml

            return yaml.safe_load(raw)  # type: ignore[no-any-return]
        except ImportError:
            # pyyaml not installed — try treating it as JSON anyway, then give a clear error
            print(
                "YAML manifest found but pyyaml is not installed.\n"
                "Install it with: pip install pyyaml",
                file=sys.stderr,
            )
            sys.exit(10)
        except Exception as exc:
            print(f"Could not parse YAML manifest: {exc}", file=sys.stderr)
            sys.exit(10)

    try:
        data: dict[str, Any] = json.loads(raw)
        return data
    except json.JSONDecodeError as exc:
        print(f"Could not parse manifest JSON: {exc}", file=sys.stderr)
        sys.exit(10)


def _print_scan_header(manifest_path: str, mode: str) -> None:
    """Print the trust/safety boundary header. Shown on every scan — local and cloud."""
    print()
    print("AgentGuard")
    print("─" * 48)
    print(f"  Manifest: {manifest_path}")
    print(f"  Mode:     {mode}")
    print()
    print("  Safety boundary:")
    print("  🔒  Real tools executed:        0")
    print("  🔒  External APIs called:       0")
    print("  🔒  Environment variables read: 0")
    print("  🔒  Production data accessed:   0")
    print()


def _emit(outcome: Outcome, args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        print(outcome.to_json())
    else:
        print(outcome.render())
    sarif_path = getattr(args, "sarif", None)
    if sarif_path and outcome.sarif is not None:
        Path(sarif_path).write_text(json.dumps(outcome.sarif, indent=2))
        print(f"wrote SARIF -> {sarif_path}", file=sys.stderr)

    html_path = getattr(args, "html", None)
    if html_path and outcome.report is not None:
        from agentguard_cli.report import render_html

        Path(html_path).write_text(render_html(outcome.report))
        print(f"wrote HTML report -> {html_path}", file=sys.stderr)

    report_json_path = getattr(args, "report_json", None)
    if report_json_path and outcome.report is not None:
        from agentguard_cli.report import render_json

        Path(report_json_path).write_text(render_json(outcome.report))
        print(f"wrote JSON report -> {report_json_path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "fingerprint":
        outcome = do_fingerprint(args.manifest)
        if outcome.decision == "error":
            print(outcome.reason, file=sys.stderr)
        else:
            print(outcome.fingerprint)
        return outcome.exit_code

    if args.command == "init":
        from agentguard_cli.commands import do_init

        return do_init(args.dir)

    if args.command in ("scan", "evaluate"):
        manifest, manifest_path = _load_manifest(getattr(args, "manifest", None))

        if getattr(args, "local", False):
            # --- Local path: fully offline, no API server required ---
            # V1 local is STATIC CHECK only (no local live-model runner). Behavioural
            # scenarios are skipped, not faked — see local.do_local_scan.
            from agentguard_cli.local import do_local_scan

            _print_scan_header(manifest_path, "STATIC CHECK (offline — no model executed)")
            local_out = do_local_scan(
                manifest,
                agent_name=getattr(args, "agent", "") or "",
                mode="static",
                allow_incomplete_static=getattr(args, "allow_incomplete_static", False),
            )
            _emit_local(local_out, args, manifest_path)
            return local_out.exit_code

        # --- Cloud path: unchanged ---
        _print_scan_header(manifest_path, "cloud")
        api, http = _client(args)
        try:
            outcome = do_scan(
                api,
                agent=args.agent,
                manifest=manifest,
                environment=args.environment,
                runner=args.runner,
                import_library=args.import_library,
                fail_on=args.fail_on,
                manifest_uri=Path(manifest_path).name,
            )
        finally:
            http.close()
        _emit(outcome, args)
        return outcome.exit_code

    if args.command == "report":
        api, http = _client(args)
        try:
            outcome = do_report(
                api,
                agent=args.agent,
                fingerprint=args.fingerprint,
                environment=args.environment,
                fail_on=args.fail_on,
            )
        finally:
            http.close()
        _emit(outcome, args)
        return outcome.exit_code

    if args.command == "policy":
        api, http = _client(args)
        try:
            outcome = do_policy_check(api, agent=args.agent, environment=args.environment)
        finally:
            http.close()
        _emit(outcome, args)
        return outcome.exit_code

    return 10  # unreachable: subparsers are required


_RESULT_TAG = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP"}


def _emit_local(out: Any, args: argparse.Namespace | None = None, manifest_path: str = "") -> None:
    """Render a LocalOutcome honestly, then write any requested machine artifacts.

    The rendering never implies behaviour was tested when it was not: the execution mode
    prefixes every finding line, skipped scenarios show why, and there is no "SAFE TO
    DEPLOY" banner — a STATIC CHECK cannot certify deployment.
    """
    from agentguard_cli.local import local_report_dict

    mode_tag = out.execution_mode.upper()  # STATIC | LIVE

    if out.decision == "error":
        print("  RESULT:  ERROR")
        print(f"  Reason:  {out.reason}")
        print()
        return

    # Structural checks (what static mode CAN evaluate)
    print("  STATIC CHECKS")
    for c in out.structural_checks:
        mark = "✓" if c.passed else "✗"
        extra = f"  ({c.detail})" if c.detail else ""
        print(f"    {mark} {c.description}{extra}")
    print()

    # Behavioural scenarios — each line carries the mode so a copied line is unambiguous.
    print("  BEHAVIOUR SCENARIOS")
    for p in out.proofs:
        tag = _RESULT_TAG.get(p.result, p.result.upper())
        line = f"    [{mode_tag}] {tag}  {p.name}  ({p.asi_id})"
        print(line)
        if p.result == "skipped":
            print(f"           ↳ skipped: {p.skip_reason}")
        elif p.result == "fail":
            pc = p.policy_check or {}
            print(f"           ↳ expected: {p.expected_behavior}")
            print(f"           ↳ observed: {pc.get('observed', p.observed_behavior)}")
    print()
    print("─" * 48)

    # Verdict
    if out.decision == "blocked":
        print("  DEPLOYMENT:  BLOCKED  ⛔")
    elif out.decision == "incomplete":
        print("  DEPLOYMENT:  INCOMPLETE  ⏭  (behavioural coverage not run)")
    elif out.incomplete:
        print("  DEPLOYMENT:  ALLOWED (PARTIAL)  ⚠  — static only, behavioural skipped")
    else:
        print("  DEPLOYMENT:  ALLOWED  ✓")
    if out.reason:
        print(f"  Reason:  {out.reason}")

    # Coverage — a vector, never a score. Loudly names what was NOT tested.
    cov = out.coverage
    if cov is not None:
        print()
        print(
            f"  Coverage:  {cov.evaluated} evaluated · {cov.failed} failed · "
            f"{cov.skipped} skipped   (mode: {out.execution_mode})"
        )
        if cov.asi_tags:
            print(f"  ASI tags:  {', '.join(cov.asi_tags)}   (tags, not a coverage %)")
        if cov.untested_surfaces:
            print(f"  NOT tested: {', '.join(cov.untested_surfaces)}")

    print()
    if out.fingerprint:
        print(f"  Fingerprint:     {out.fingerprint[:16]}...")
    if out.evidence_digest:
        digest = out.evidence_digest[:23]
        print(f"  Evidence digest: {digest}...  (reproducibility, not tamper-proof)")
    print(f"  Time:            {out.elapsed_ms / 1000:.1f}s")
    print("─" * 48)
    print()

    # Machine artifacts
    if args is None:
        return
    report = local_report_dict(out)
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    report_json_path = getattr(args, "report_json", None)
    if report_json_path:
        Path(report_json_path).write_text(json.dumps(report, indent=2))
        print(f"wrote JSON report -> {report_json_path}", file=sys.stderr)
    sarif_path = getattr(args, "sarif", None)
    if sarif_path:
        from agentguard_cli.sarif import build_local_sarif

        sarif = build_local_sarif(out, manifest_uri=Path(manifest_path).name or "agent-manifest")
        Path(sarif_path).write_text(json.dumps(sarif, indent=2))
        print(f"wrote SARIF -> {sarif_path}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
