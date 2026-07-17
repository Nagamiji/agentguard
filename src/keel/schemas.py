import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from keel.evals.taxonomy import ScenarioCategory


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OnboardingInput(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)


class OnboardingOut(BaseModel):
    organization_id: uuid.UUID
    api_key: str = Field(description="Shown once. Store it now — it cannot be retrieved later.")
    next_steps: str


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    revoked_at: datetime | None = None


class ApiKeyIssued(BaseModel):
    key: ApiKeyOut
    api_key: str = Field(description="Shown once. Store it now — it cannot be retrieved later.")


class OrgBootstrapOut(BaseModel):
    organization: OrgOut
    api_key: str = Field(description="Shown once. Store it now — it cannot be retrieved later.")


class ApiKeyCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        allowed = {"*", "admin", "read", "write", "scan"}
        for s in v:
            if s not in allowed:
                raise ValueError(f"Invalid scope '{s}', must be one of {sorted(allowed)}")
        return v


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    created_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="Stable handle. Derived from name when omitted; cannot be changed later.",
    )
    description: str | None = None
    framework: str | None = Field(default=None, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    """Cosmetic fields only. `slug` is absent on purpose — it is the stable handle."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: Literal["active", "archived"] | None = None
    metadata: dict[str, Any] | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    framework: str | None
    status: str
    metadata: dict[str, Any] = Field(validation_alias="agent_metadata")
    created_at: datetime
    updated_at: datetime


class AgentVersionCreate(BaseModel):
    manifest: dict[str, Any] = Field(
        description=(
            "Agent configuration. Behaviour-relevant fields (prompts, tools, model, params, "
            "retrieval, framework) are canonicalised and hashed into the fingerprint; "
            "everything else is stored but not hashed."
        )
    )


class AgentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    sequence_number: int
    fingerprint: str
    fingerprint_algo: str
    manifest: dict[str, Any]
    created_at: datetime


class AliasUpsert(BaseModel):
    version_id: uuid.UUID


class AliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    version_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str | None = None
    # The taxonomy the library is organised around (keel/evals/taxonomy.py).
    category: ScenarioCategory
    input: dict[str, Any]
    checks: list[dict[str, Any]] = Field(min_length=1)
    enabled: bool = True


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    category: str
    input: dict[str, Any]
    checks: list[dict[str, Any]]
    enabled: bool
    source: str
    library_version: str | None
    created_at: datetime
    updated_at: datetime


class EvalRunCreate(BaseModel):
    version_id: uuid.UUID
    runner: str = Field(default="scripted", max_length=30)
    # Which environment's policy to enforce (dev/staging/prod). None applies only the
    # environment-agnostic policies.
    environment: str | None = Field(default=None, max_length=30)


class EvalResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scenario_id: uuid.UUID
    passed: bool
    failures: list[dict[str, Any]]
    output: dict[str, Any]
    duration_ms: int
    error: str | None


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    version_id: uuid.UUID
    fingerprint: str
    runner: str
    status: str
    gate_decision: str
    total_scenarios: int
    failed_scenarios: int
    environment: str | None
    policy_fingerprint: str | None
    policy_findings: list[dict[str, Any]]
    created_at: datetime


class EvalRunDetail(EvalRunOut):
    results: list[EvalResultOut] = Field(default_factory=list)


class GateOut(BaseModel):
    """The deploy verdict. This is the answer CI blocks on."""

    decision: str
    fingerprint: str
    reason: str
    run_id: uuid.UUID | None = None
    evaluated_at: datetime | None = None
    failures: list[dict[str, Any]] = Field(default_factory=list)
    # HMAC over (fingerprint, decision, run_id, evaluated_at) when signing is enabled.
    signature: str | None = None


class LibraryScenarioOut(BaseModel):
    """One attack in the built-in corpus, as metadata (no need to run it to browse it)."""

    key: str
    category: str
    severity: str
    title: str
    description: str
    attack: str
    requires_tools: bool


class LibraryOut(BaseModel):
    version: str
    count: int
    scenarios: list[LibraryScenarioOut]


class ImportResult(BaseModel):
    """Outcome of seeding an agent from the library."""

    library_version: str
    imported: int
    skipped: int
    scenarios: list[ScenarioOut]


class CategoryRiskOut(BaseModel):
    category: str
    tested: int
    failed: int
    max_severity: str | None


class RiskReport(BaseModel):
    """The aggregated verdict across a library scan — the 'what did you find' answer."""

    decision: str  # allowed | blocked | unknown (same vocabulary as the gate)
    risk_level: str
    reason: str
    fingerprint: str
    run_id: uuid.UUID | None = None
    evaluated_at: datetime | None = None
    categories: list[CategoryRiskOut] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)


# --- policy engine (Phase 4) ---


class PolicyCreate(BaseModel):
    scope_type: Literal["organization", "project", "agent"]
    # For 'organization' this is ignored (the caller's org is used). For 'agent' it must be
    # an agent id the caller owns.
    scope_id: uuid.UUID | None = None
    environment: str | None = Field(default=None, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    rules: dict[str, Any]
    note: str | None = None


class PolicyVersionCreate(BaseModel):
    rules: dict[str, Any]
    note: str | None = None


class PolicyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_id: uuid.UUID
    sequence_number: int
    rules: dict[str, Any]
    fingerprint: str
    note: str | None
    created_at: datetime


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    environment: str | None
    name: str
    created_at: datetime
    updated_at: datetime


class PolicyDetail(PolicyOut):
    versions: list[PolicyVersionOut] = Field(default_factory=list)


class PolicyCreated(BaseModel):
    policy: PolicyOut
    version: PolicyVersionOut


class EffectiveRule(BaseModel):
    value: Any
    source: str  # the scope that supplied this rule (provenance)


class CompiledPolicyOut(BaseModel):
    """The effective, compiled policy for an agent — what a scan will enforce."""

    environment: str | None
    fingerprint: str
    effective: dict[str, EffectiveRule]
    derived_checks: list[dict[str, Any]]
    manifest_findings: list[dict[str, Any]]
    deferred_runtime: list[str]
