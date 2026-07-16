import uuid
from datetime import datetime

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
