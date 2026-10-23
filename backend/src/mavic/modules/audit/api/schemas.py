"""Lo que devuelve GET /audit-events."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from mavic.modules.audit.application.audit import AuditEventView


class AuditEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_kind: str  # user, agent, system
    actor_name: str
    action: str
    level: str  # critical, info, system
    subject_kind: str | None
    subject_id: str | None
    subject_label: str | None
    summary: str
    details: dict[str, Any]

    @classmethod
    def from_view(cls, view: AuditEventView) -> "AuditEventOut":
        return cls(**view.__dict__)
