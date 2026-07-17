"""Shared row lookups for routers.

`get_agent_or_404` was copy-pasted in two routers; the policy engine would have made it
three. Consolidated here. No org filter is needed — RLS scopes the query, so another tenant's
row is invisible and 404 is both what happens and the correct answer (403 would confirm it
exists).
"""

from __future__ import annotations

import uuid

from fastapi import status
from fastapi.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.models import Agent


def get_agent_or_404(agent_id: uuid.UUID, db: Session) -> Agent:
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent
