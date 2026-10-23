"""Auditoría: quién hizo qué y cuándo (solo lectura).

Permiso VIEW_AUDIT: administración y supervisión. No hay endpoints para editar
ni borrar eventos, y la base tampoco lo permite.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.api.pagination import Limit, Offset, PageOut
from mavic.modules.audit.api.schemas import AuditEventOut
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditCategory, AuditLevel

router = APIRouter()


@router.get("/audit-events", tags=["audit"])
def list_events(
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    limit: Limit = 20,
    offset: Offset = 0,
    q: Annotated[
        str | None, Query(max_length=100, description="Texto, persona o 'Caso #12'")
    ] = None,
    category: Annotated[AuditCategory | None, Query(description="Tema del evento")] = None,
    level: Annotated[AuditLevel | None, Query(description="critical, info o system")] = None,
    since: Annotated[date | None, Query(description="Desde este día (incluido)")] = None,
    until: Annotated[date | None, Query(description="Hasta este día (incluido)")] = None,
) -> PageOut[AuditEventOut]:
    """Eventos de la empresa, del más nuevo al más viejo."""
    page = audit.list_events(
        session,
        actor=actor,
        clock=clock,
        search=q,
        category=category,
        level=level.value if level else None,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return PageOut(
        items=[AuditEventOut.from_view(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )
