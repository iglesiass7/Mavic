"""Lecturas y escrituras de la auditoría."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from mavic.modules.audit.infrastructure.orm import AuditEventModel


def _like(text: str) -> str:
    r"""Patrón para ILIKE que busca el texto TAL CUAL ("50%" no es un comodín).

    >>> _like("50%_a")
    '%50\\%\\_a%'
    """
    escaped = text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True)
class EventFilter:
    search: str | None = None
    actions: list[str] | None = None
    level: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: AuditEventModel) -> None:
        self._session.add(event)

    def page(
        self, company_id: uuid.UUID, filters: EventFilter, *, limit: int, offset: int
    ) -> tuple[list[AuditEventModel], int]:
        conditions: list[ColumnElement[bool]] = [AuditEventModel.company_id == company_id]
        if filters.search and filters.search.strip():
            pattern = _like(filters.search)
            conditions.append(
                or_(
                    AuditEventModel.summary.ilike(pattern, escape="\\"),
                    AuditEventModel.subject_label.ilike(pattern, escape="\\"),
                    AuditEventModel.actor_name.ilike(pattern, escape="\\"),
                )
            )
        if filters.actions is not None:
            conditions.append(AuditEventModel.action.in_(filters.actions))
        if filters.level:
            conditions.append(AuditEventModel.level == filters.level)
        if filters.since is not None:
            conditions.append(AuditEventModel.occurred_at >= filters.since)
        if filters.until is not None:
            conditions.append(AuditEventModel.occurred_at < filters.until)

        total = self._session.scalar(
            select(func.count()).select_from(AuditEventModel).where(*conditions)
        )
        events = self._session.scalars(
            select(AuditEventModel)
            .where(*conditions)
            .order_by(AuditEventModel.seq.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(events), int(total or 0)
