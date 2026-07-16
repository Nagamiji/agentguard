import re
import uuid

from fastapi import APIRouter, Query, Response, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select

from keel.deps import CurrentOrg, DbSession
from keel.evals.checks import CheckError, validate_checks
from keel.evals.engine import GateDecision, RunStatus, decide, run_scenario
from keel.evals.runner import RunnerError, get_runner
from keel.models import Agent, AgentVersion, EvalResult, EvalRun, EvalScenario
from keel.schemas import (
    EvalResultOut,
    EvalRunCreate,
    EvalRunDetail,
    EvalRunOut,
    GateOut,
    ScenarioCreate,
    ScenarioOut,
)

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
    agent_id: uuid.UUID, payload: ScenarioCreate, org_id: CurrentOrg, db: DbSession
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
        category=payload.category,
        input=payload.input,
        checks=payload.checks,
        enabled=payload.enabled,
    )
    db.add(scenario)
    db.commit()
    return ScenarioOut.model_validate(scenario)


@router.get("/agents/{agent_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(agent_id: uuid.UUID, org_id: CurrentOrg, db: DbSession) -> list[ScenarioOut]:
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
    agent_id: uuid.UUID, scenario_id: uuid.UUID, org_id: CurrentOrg, db: DbSession
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
    "/agents/{agent_id}/runs", response_model=EvalRunDetail, status_code=status.HTTP_201_CREATED
)
def create_run(
    agent_id: uuid.UUID, payload: EvalRunCreate, org_id: CurrentOrg, db: DbSession
) -> EvalRunDetail:
    """Evaluate a version against every enabled scenario.

    Synchronous on purpose for now. The ScriptedRunner is in-memory and returns in
    microseconds, so a queue would add moving parts and a whole class of "the job vanished"
    bugs to buy nothing. When real model execution lands (EVAL-02) the runtime becomes
    seconds-to-minutes and this moves to the worker — that is the moment a queue earns its
    complexity, not before.
    """
    agent = _get_agent(agent_id, db)

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

    results = [run_scenario(runner, version.manifest, s.id, s.input, s.checks) for s in scenarios]
    run_status, gate_decision = decide(results)

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
    )
    db.add(run)
    db.flush()  # need run.id before inserting results

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
def list_runs(agent_id: uuid.UUID, org_id: CurrentOrg, db: DbSession) -> list[EvalRunOut]:
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
    agent_id: uuid.UUID, run_id: uuid.UUID, org_id: CurrentOrg, db: DbSession
) -> EvalRunDetail:
    agent = _get_agent(agent_id, db)
    run = db.execute(
        select(EvalRun).where(EvalRun.id == run_id, EvalRun.agent_id == agent.id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return _run_detail(run, db)


@router.get("/agents/{agent_id}/gate", response_model=GateOut)
def gate(
    agent_id: uuid.UUID,
    org_id: CurrentOrg,
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
    )
