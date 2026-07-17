from fastapi import APIRouter, status
from sqlalchemy import select

from keel.deps import DbSession, ReadOrg, WriteOrg
from keel.models import Project
from keel.schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/v1", tags=["projects"])


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, org_id: WriteOrg, db: DbSession) -> ProjectOut:
    project = Project(organization_id=org_id, name=payload.name)
    db.add(project)
    db.commit()
    return ProjectOut.model_validate(project)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(org_id: ReadOrg, db: DbSession) -> list[ProjectOut]:
    """List this organization's projects.

    NOTE the deliberate absence of `.where(Project.organization_id == org_id)`.
    Row-Level Security scopes this query inside Postgres. This is not laziness —
    it is the isolation test: if the engine were not enforcing tenancy, this
    endpoint would leak every tenant's projects, and tests/test_isolation.py
    would fail loudly.
    """
    rows = db.execute(select(Project).order_by(Project.created_at)).scalars().all()
    return [ProjectOut.model_validate(r) for r in rows]
