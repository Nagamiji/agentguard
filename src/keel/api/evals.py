import logging
import re
import time
import uuid

from fastapi import APIRouter, Query, Response, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select

from keel.api.policy_service import effective_policy
from keel.context import set_run_id
from keel.deps import DbSession, ReadOrg, ScanOrg, WriteOrg
from keel.evals.checks import CheckError, validate_checks
from keel.evals.engine import GateDecision, RunStatus, decide, run_scenario
from keel.evals.library import LIBRARY_VERSION, all_scenarios, concrete_input, scenarios_for
from keel.evals.risk import ResultView, classify
from keel.evals.runner import RunnerError, get_runner
from keel.metrics import metrics
from keel.models import Agent, AgentVersion, EvalResult, EvalRun, EvalScenario
from keel.policy import fingerprint_rules
from keel.policy.resolver import effective_values
from keel.rate_limit import rate_limited
from keel.schemas import (
    CategoryRiskOut,
    EvalResultOut,
    EvalRunCreate,
    EvalRunDetail,
    EvalRunOut,
    GateOut,
    ImportResult,
    LibraryOut,
    LibraryScenarioOut,
    RiskReport,
    ScenarioCreate,
    ScenarioOut,
)
from keel.signing import sign_verdict

logger = logging.getLogger("evals")
router = APIRouter(prefix="/v1", tags=["evals"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "scenario"


def _get_agent(agent_id: uuid.UUID, db: DbSession) -> Agent:
    # No org filter — RLS scopes this; another tenant's agent is invisible, so 404 is both
    # what happens and the right answer (403 would confirm it exists).
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


@router.post(
    "/agents/{agent_id}/scenarios", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED
)
def create_scenario(
    agent_id: uuid.UUID, payload: ScenarioCreate, org_id: WriteOrg, db: DbSession
) -> ScenarioOut:
    agent = _get_agent(agent_id, db)

    # Validate at write time, not run time. A malformed check that silently never fires
    # would report a pass for something that was never tested — the worst failure this
    # product can have.
    try:
        validate_checks(payload.checks)
    except CheckError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    slug = payload.slug or _slugify(payload.name)
    if db.execute(
        select(EvalScenario).where(EvalScenario.agent_id == agent.id, EvalScenario.slug == slug)
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Scenario '{slug}' already exists")

    scenario = EvalScenario(
        organization_id=org_id,
        agent_id=agent.id,
        slug=slug,
        name=payload.name,
        description=payload.description,
        category=str(payload.category),
        input=payload.input,
        checks=payload.checks,
        enabled=payload.enabled,
        source="custom",
    )
    db.add(scenario)
    db.commit()
    return ScenarioOut.model_validate(scenario)


@router.get("/agents/{agent_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(agent_id: uuid.UUID, org_id: ReadOrg, db: DbSession) -> list[ScenarioOut]:
    agent = _get_agent(agent_id, db)
    rows = (
        db.execute(
            select(EvalScenario)
            .where(EvalScenario.agent_id == agent.id)
            .order_by(EvalScenario.created_at)
        )
        .scalars()
        .all()
    )
    return [ScenarioOut.model_validate(r) for r in rows]


@router.delete("/agents/{agent_id}/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    agent_id: uuid.UUID, scenario_id: uuid.UUID, org_id: WriteOrg, db: DbSession
) -> Response:
    agent = _get_agent(agent_id, db)
    scenario = db.execute(
        select(EvalScenario).where(
            EvalScenario.id == scenario_id, EvalScenario.agent_id == agent.id
        )
    ).scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")
    db.delete(scenario)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/agents/{agent_id}/runs",
    response_model=EvalRunDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[rate_limited("scans")],
)
def create_run(
    agent_id: uuid.UUID, payload: EvalRunCreate, org_id: ScanOrg, db: DbSession
) -> EvalRunDetail:
    """Evaluate a version against every enabled scenario.

    Synchronous on purpose for now. The ScriptedRunner is in-memory and returns in
    microseconds, so a queue would add moving parts and a whole class of "the job vanished"
    bugs to buy nothing. When real model execution lands (EVAL-02) the runtime becomes
    seconds-to-minutes and this moves to the worker — that is the moment a queue earns its
    complexity, not before.
    """
    agent = _get_agent(agent_id, db)

    # Billing boundary validation
    from sqlalchemy import func

    from keel.models import Organization, Plan, UsageEvent

    org = db.get(Organization, org_id)
    if org and org.plan_id:
        plan = db.get(Plan, org.plan_id)
    else:
        plan = db.execute(select(Plan).where(Plan.name == "free")).scalar_one_or_none()

    if plan:
        scan_count = (
            db.execute(
                select(func.count(UsageEvent.id)).where(
                    UsageEvent.organization_id == org_id,
                    UsageEvent.event_type == "scan_executed",
                )
            ).scalar()
            or 0
        )
        if plan.scan_limit >= 0 and scan_count >= plan.scan_limit:
            msg = (
                f"Scan limit reached ({plan.scan_limit}) for plan '{plan.name}'. "
                "Please upgrade to run more scans."
            )
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, msg)

    version = db.execute(
        select(AgentVersion).where(
            AgentVersion.id == payload.version_id, AgentVersion.agent_id == agent.id
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent version not found")

    try:
        runner = get_runner(payload.runner)
    except RunnerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    scenarios = (
        db.execute(
            select(EvalScenario)
            .where(EvalScenario.agent_id == agent.id, EvalScenario.enabled.is_(True))
            .order_by(EvalScenario.created_at)
        )
        .scalars()
        .all()
    )

    # Compile the effective policy and let the engine CONSUME it rather than hardcoding
    # limits: policy-derived checks are merged into every scenario, and static violations of
    # the declared manifest (e.g. a disallowed provider) are decided without a run.
    resolved, compiled = effective_policy(
        db, org_id, agent.id, payload.environment, version.manifest
    )
    policy_checks = compiled.derived_checks
    policy_findings = compiled.manifest_findings
    policy_fingerprint = fingerprint_rules(effective_values(resolved)) if resolved else None

    # Structured Logging: evaluation started
    logger.info(
        "Evaluation started",
        extra={
            "event_type": "evaluation_started",
            "agent_id": str(agent_id),
            "version_id": str(version.id),
            "runner": payload.runner,
            "environment": payload.environment or "none",
            "policy_fingerprint": policy_fingerprint or "none",
            "scenarios_count": len(scenarios),
        },
    )

    # Record scenario total metrics
    for s in scenarios:
        metrics.scenarios_total.inc(labels={"category": str(s.category)})

    start_time = time.perf_counter()
    results = [
        run_scenario(runner, version.manifest, s.id, s.input, [*s.checks, *policy_checks])
        for s in scenarios
    ]
    duration_sec = time.perf_counter() - start_time

    run_status, gate_decision = decide(results)

    # Record failed scenario metrics
    for r in results:
        if not r.passed:
            scen = next((s for s in scenarios if s.id == r.scenario_id), None)
            category = scen.category if scen else "unknown"
            metrics.scenarios_failed_total.inc(labels={"category": str(category)})

    # A static policy violation is definitive: it blocks even a run with no scenarios or one
    # whose scenarios could not complete. Fail closed.
    if any(f.get("severity") in ("critical", "high") for f in policy_findings):
        run_status, gate_decision = RunStatus.FAILED, GateDecision.BLOCKED
        for finding in policy_findings:
            metrics.policy_violations_total.inc(
                labels={
                    "rule_type": finding.get("type", "unknown"),
                    "environment": payload.environment or "none",
                }
            )

    run = EvalRun(
        organization_id=org_id,
        agent_id=agent.id,
        version_id=version.id,
        fingerprint=version.fingerprint,
        runner=payload.runner,
        status=str(run_status),
        gate_decision=str(gate_decision),
        total_scenarios=len(results),
        failed_scenarios=sum(1 for r in results if not r.passed),
        environment=payload.environment,
        policy_fingerprint=policy_fingerprint,
        policy_findings=policy_findings,
    )
    db.add(run)
    db.flush()  # need run.id before inserting results

    # Record usage event
    db.add(
        UsageEvent(
            organization_id=org_id,
            event_type="scan_executed",
            event_metadata={
                "agent_id": str(agent.id),
                "run_id": str(run.id),
                "decision": str(gate_decision),
                "total_scenarios": len(results),
                "failed_scenarios": sum(1 for r in results if not r.passed),
            },
        )
    )

    # Set run_id context variable
    set_run_id(str(run.id))

    # Record run metrics
    metrics.eval_runs_total.inc(
        labels={
            "decision": str(gate_decision),
            "runner": payload.runner,
            "environment": payload.environment or "none",
        }
    )
    metrics.eval_run_duration_seconds.observe(
        duration_sec,
        labels={"runner": payload.runner, "environment": payload.environment or "none"},
    )

    rows = [
        EvalResult(
            organization_id=org_id,
            run_id=run.id,
            scenario_id=result.scenario_id,
            passed=result.passed,
            failures=[f.as_dict() for f in result.failures],
            output=result.output,
            duration_ms=result.duration_ms,
            error=result.error,
        )
        for result in results
    ]
    for row in rows:
        db.add(row)

    db.commit()

    # Structured Logging: evaluation completed
    model_info = version.manifest.get("model", {})
    model_provider = (
        model_info.get("provider", "unknown") if isinstance(model_info, dict) else "unknown"
    )
    model_id = model_info.get("id", "unknown") if isinstance(model_info, dict) else "unknown"

    logger.info(
        "Evaluation completed",
        extra={
            "event_type": "evaluation_completed",
            "agent_id": str(agent_id),
            "version_id": str(version.id),
            "run_id": str(run.id),
            "gate_decision": str(gate_decision),
            "total_scenarios": len(results),
            "failed_scenarios": sum(1 for r in results if not r.passed),
            "environment": payload.environment or "none",
            "model_provider": model_provider,
            "model_id": model_id,
            "run_status": str(run_status),
        },
    )

    if gate_decision == GateDecision.BLOCKED:
        logger.warning(
            "Evaluation blocked deployment",
            extra={
                "event_type": "blocked_decision",
                "agent_id": str(agent_id),
                "version_id": str(version.id),
                "run_id": str(run.id),
                "policy_findings": policy_findings,
                "failed_scenarios_count": sum(1 for r in results if not r.passed),
            },
        )

    # Dynamic policy violations logging
    for r in results:
        for failure in r.failures:
            check_type = getattr(failure, "check_type", "unknown")
            metrics.policy_violations_total.inc(
                labels={
                    "rule_type": check_type,
                    "environment": payload.environment or "none",
                }
            )
            logger.warning(
                "Policy violation detected",
                extra={
                    "event_type": "policy_violation",
                    "agent_id": str(agent_id),
                    "version_id": str(version.id),
                    "run_id": str(run.id),
                    "check_type": check_type,
                    "severity": getattr(failure, "severity", "unknown"),
                    "detail": getattr(failure, "detail", ""),
                },
            )

    # Build the response from the objects we already hold, NOT by re-querying.
    #
    # The tenant GUC is set with set_config(..., is_local=true) — transaction-local — so
    # db.commit() discards it. A SELECT on a tenant table after this point evaluates the
    # RLS policy as ''::uuid and raises a DataError.
    #
    # That error is protective and must not be "fixed" by loosening the policy: if the
    # policy silently returned zero rows instead, this endpoint would report a run with no
    # failures — and the gate would read that as ALLOWED. Failing loudly is correct; the
    # right response is to not query after commit. (expire_on_commit=False, so these
    # objects are still readable without a refresh.)
    detail = EvalRunDetail.model_validate(run)
    detail.results = [EvalResultOut.model_validate(r) for r in rows]
    return detail


def _run_detail(run: EvalRun, db: DbSession) -> EvalRunDetail:
    """Only safe where no commit has happened in this request — see create_run."""
    rows = (
        db.execute(select(EvalResult).where(EvalResult.run_id == run.id).order_by(EvalResult.id))
        .scalars()
        .all()
    )
    detail = EvalRunDetail.model_validate(run)
    detail.results = [EvalResultOut.model_validate(r) for r in rows]
    return detail


@router.get("/agents/{agent_id}/runs", response_model=list[EvalRunOut])
def list_runs(agent_id: uuid.UUID, org_id: ReadOrg, db: DbSession) -> list[EvalRunOut]:
    agent = _get_agent(agent_id, db)
    rows = (
        db.execute(
            select(EvalRun).where(EvalRun.agent_id == agent.id).order_by(EvalRun.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [EvalRunOut.model_validate(r) for r in rows]


@router.get("/agents/{agent_id}/runs/{run_id}", response_model=EvalRunDetail)
def get_run(
    agent_id: uuid.UUID, run_id: uuid.UUID, org_id: ReadOrg, db: DbSession
) -> EvalRunDetail:
    agent = _get_agent(agent_id, db)
    run = db.execute(
        select(EvalRun).where(EvalRun.id == run_id, EvalRun.agent_id == agent.id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return _run_detail(run, db)


@router.get(
    "/agents/{agent_id}/gate",
    response_model=GateOut,
    dependencies=[rate_limited("scans")],
)
def gate(
    agent_id: uuid.UUID,
    org_id: ScanOrg,
    db: DbSession,
    fingerprint: str = Query(description="The exact configuration being deployed."),
) -> GateOut:
    """May this exact configuration deploy?

    The whole product in one endpoint. It answers by fingerprint, not by version id or
    alias: a verdict belongs to a configuration, and "we tested something called v3" is not
    a claim about the bytes you are about to ship (cf. MLflow #8078, where an explicit pin
    silently resolved to latest).

    Fails closed. An unevaluated fingerprint is UNKNOWN, never ALLOWED — an agent nobody
    tested is not an agent known to be safe, and this endpoint must never be the reason a
    dangerous deploy went out.
    """
    agent = _get_agent(agent_id, db)

    run = db.execute(
        select(EvalRun)
        .where(EvalRun.agent_id == agent.id, EvalRun.fingerprint == fingerprint)
        .order_by(EvalRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if run is None:
        return GateOut(
            decision=str(GateDecision.UNKNOWN),
            fingerprint=fingerprint,
            reason=(
                "This configuration has never been evaluated. Run an evaluation before "
                "deploying it."
            ),
            signature=sign_verdict(fingerprint, str(GateDecision.UNKNOWN)),
        )

    failures = [
        failure
        for result in db.execute(
            select(EvalResult).where(EvalResult.run_id == run.id, EvalResult.passed.is_(False))
        )
        .scalars()
        .all()
        for failure in result.failures
    ]
    # Static policy violations are part of the verdict too — they blocked at run time and
    # must appear in the evidence the gate returns.
    failures.extend(run.policy_findings or [])

    if run.status == str(RunStatus.ERRORED):
        reason = "The evaluation could not complete, so safety is unknown. Investigate and re-run."
    elif run.gate_decision == str(GateDecision.BLOCKED):
        reason = (
            f"{run.failed_scenarios} of {run.total_scenarios} scenarios failed with "
            "blocking severity."
        )
    elif failures:
        reason = (
            f"{run.failed_scenarios} of {run.total_scenarios} scenarios reported non-blocking "
            "findings."
        )
    else:
        reason = f"All {run.total_scenarios} scenarios passed."

    return GateOut(
        decision=run.gate_decision,
        fingerprint=fingerprint,
        reason=reason,
        run_id=run.id,
        evaluated_at=run.created_at,
        failures=failures,
        signature=sign_verdict(fingerprint, run.gate_decision, str(run.id)),
    )


# --- the failure scenario library (Phase 3) ---------------------------------------------


@router.get("/library", response_model=LibraryOut)
def get_library(org_id: ReadOrg) -> LibraryOut:
    """Browse the built-in attack corpus. Static content — the moat, made inspectable."""
    scenarios = all_scenarios()
    return LibraryOut(
        version=LIBRARY_VERSION,
        count=len(scenarios),
        scenarios=[
            LibraryScenarioOut(
                key=s.key,
                category=str(s.category),
                severity=str(s.severity),
                title=s.title,
                description=s.description,
                attack=s.attack,
                requires_tools=s.requires_tools,
            )
            for s in scenarios
        ],
    )


@router.post(
    "/agents/{agent_id}/scenarios/import",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
def import_library(agent_id: uuid.UUID, org_id: WriteOrg, db: DbSession) -> ImportResult:
    """Seed an agent with the built-in library.

    Idempotent by slug (= library key): re-importing skips what is already present rather
    than duplicating, so a customer can pull in new attacks as the corpus grows without
    losing edits to the ones they already have.
    """
    agent = _get_agent(agent_id, db)

    # Tool-requiring probes need the agent's declared tool names. Take them from the latest
    # version; an agent with no version yet simply gets the universal probes.
    latest = db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.sequence_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    tool_names: list[str] = []
    if latest is not None:
        for tool in latest.manifest.get("tools") or []:
            if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                tool_names.append(tool["name"])

    existing = set(
        db.execute(select(EvalScenario.slug).where(EvalScenario.agent_id == agent.id))
        .scalars()
        .all()
    )

    created: list[EvalScenario] = []
    skipped = 0
    for lib in scenarios_for(tool_names):
        if lib.key in existing:
            skipped += 1
            continue
        scenario = EvalScenario(
            organization_id=org_id,
            agent_id=agent.id,
            slug=lib.key,
            name=lib.title,
            description=lib.description,
            category=str(lib.category),
            input=concrete_input(lib, tool_names),
            checks=lib.checks,
            enabled=True,
            source="library",
            library_version=LIBRARY_VERSION,
        )
        db.add(scenario)
        created.append(scenario)

    db.commit()
    # Built from held objects, not re-queried: the tenant GUC is transaction-local and the
    # commit above discarded it (see create_run for the full note).
    return ImportResult(
        library_version=LIBRARY_VERSION,
        imported=len(created),
        skipped=skipped,
        scenarios=[ScenarioOut.model_validate(s) for s in created],
    )


@router.get(
    "/agents/{agent_id}/risk",
    response_model=RiskReport,
    dependencies=[rate_limited("scans")],
)
def risk_report(
    agent_id: uuid.UUID,
    org_id: ScanOrg,
    db: DbSession,
    fingerprint: str = Query(description="The exact configuration whose risk you want."),
) -> RiskReport:
    """The aggregated verdict across the most recent scan of this configuration.

    Fails closed like the gate: a configuration that was never scanned is `unknown`, never a
    clean bill of health.
    """
    agent = _get_agent(agent_id, db)

    run = db.execute(
        select(EvalRun)
        .where(EvalRun.agent_id == agent.id, EvalRun.fingerprint == fingerprint)
        .order_by(EvalRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if run is None:
        return RiskReport(
            decision="unknown",
            risk_level="unknown",
            reason="This configuration has never been evaluated. Run a scan before deploying it.",
            fingerprint=fingerprint,
        )

    # Join results to their scenario's category. Both tables are RLS-scoped and this GET has
    # not committed, so the tenant GUC is still set — the query is correctly tenant-bound.
    rows = db.execute(
        select(EvalResult, EvalScenario.category)
        .join(EvalScenario, EvalScenario.id == EvalResult.scenario_id)
        .where(EvalResult.run_id == run.id)
    ).all()

    views = [
        ResultView(
            category=category,
            passed=result.passed,
            failures=result.failures or [],
            errored=bool(result.error),
        )
        for result, category in rows
    ]
    # A static policy violation is a finding in its own right, independent of any scenario.
    if run.policy_findings:
        views.append(
            ResultView(category="policy_violation", passed=False, failures=run.policy_findings)
        )
    summary = classify(views)

    return RiskReport(
        decision=summary.decision,
        risk_level=summary.risk_level,
        reason=summary.reason,
        fingerprint=fingerprint,
        run_id=run.id,
        evaluated_at=run.created_at,
        categories=[
            CategoryRiskOut(
                category=c.category, tested=c.tested, failed=c.failed, max_severity=c.max_severity
            )
            for c in summary.categories
        ],
        findings=summary.findings,
    )


@router.get("/runs", response_model=list[EvalRunOut])
def list_org_runs(org_id: ReadOrg, db: DbSession) -> list[EvalRunOut]:
    """List all evaluation runs across all agents for the organization."""
    rows = db.execute(select(EvalRun).order_by(EvalRun.created_at.desc())).scalars().all()
    return [EvalRunOut.model_validate(r) for r in rows]
