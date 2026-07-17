"""`agentguard` entry point: parse args, call the API, print, and exit with the CI code."""

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
        p.add_argument("--agent", required=True, help="agent id or slug")
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
        s.add_argument("--manifest", required=True, help="path to the agent manifest JSON")
        s.add_argument("--runner", default="scripted", help="evaluation runner (scripted|vertex)")
        s.add_argument(
            "--import-library",
            action="store_true",
            help="seed the built-in attack library before scanning",
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
        try:
            manifest = json.loads(Path(args.manifest).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"could not read manifest: {exc}", file=sys.stderr)
            return 10
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
                manifest_uri=Path(args.manifest).name,
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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
