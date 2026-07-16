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
