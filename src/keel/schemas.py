import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


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
    category: Literal[
        "unsafe_tool_use", "prompt_injection", "data_leakage", "non_compliance", "hallucination"
    ]
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
    created_at: datetime
    updated_at: datetime


class EvalRunCreate(BaseModel):
    version_id: uuid.UUID
    runner: str = Field(default="scripted", max_length=30)


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
