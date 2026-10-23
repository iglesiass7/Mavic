"""Casos de uso de la auditoría: registrar un evento y listarlos.

`record` lo llaman los otros módulos ANTES de su `commit`: el evento viaja en la
misma transacción que el cambio. No confirma nada por su cuenta.

    def update_rule(...):
        ... cambia la regla ...
        audit.record(session, company_id=..., actor=actor, action=RULE_UPDATED, ...)
        session.commit()          # la regla y su evento, juntos

La auditoría no conoce a los otros módulos: recibe todo lo que guarda
(quién, qué, sobre qué) ya armado.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.audit.domain.events import (
    LEVEL,
    ActorKind,
    AuditAction,
    AuditCategory,
    Subject,
    actions_in,
)
from mavic.modules.audit.infrastructure.orm import AuditEventModel
from mavic.modules.audit.infrastructure.repositories import AuditRepository, EventFilter
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission

# Cómo se muestran los que no son personas.
AGENT_NAME = "Agente IA"
SYSTEM_NAME = "Sistema"


def record(
    session: Session,
    *,
    company_id: uuid.UUID | None,
    action: AuditAction,
    summary: str,
    actor: Actor | None = None,
    actor_kind: ActorKind | None = None,
    subject: Subject | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Agrega un evento a la transacción en curso (no hace commit).

    Con `actor`, lo hizo esa persona. Sin `actor`, lo hizo el agente o el sistema
    (`actor_kind`).
    """
    if actor is not None:
        kind, user_id, name = ActorKind.USER, actor.user_id, actor.name or "Usuario"
    else:
        kind = actor_kind or ActorKind.SYSTEM
        user_id, name = None, AGENT_NAME if kind == ActorKind.AGENT else SYSTEM_NAME
    AuditRepository(session).add(
        AuditEventModel(
            company_id=company_id,
            actor_kind=kind.value,
            actor_user_id=user_id,
            actor_name=name,
            action=action.value,
            level=LEVEL[action].value,
            subject_kind=subject.kind if subject else None,
            subject_id=subject.id if subject else None,
            subject_label=subject.label if subject else None,
            summary=summary,
            details=details or {},
        )
    )


# ---------------------------------------------------------------- pantalla


@dataclass(frozen=True)
class AuditEventView:
    id: uuid.UUID
    occurred_at: datetime
    actor_kind: str
    actor_name: str
    action: str
    level: str
    subject_kind: str | None
    subject_id: str | None
    subject_label: str | None
    summary: str
    details: dict[str, Any]


@dataclass(frozen=True)
class AuditPage:
    items: list[AuditEventView]
    total: int
    limit: int
    offset: int


def list_events(
    session: Session,
    *,
    actor: Actor,
    clock: Clock,
    search: str | None,
    category: AuditCategory | None,
    level: str | None,
    since: date | None,
    until: date | None,
    limit: int,
    offset: int,
) -> AuditPage:
    """Eventos de la empresa, del más nuevo al más viejo.

    `since` y `until` son días (hora argentina), los dos incluidos.
    """
    actor.require(Permission.VIEW_AUDIT)
    company_id = actor.require_company()
    zone = clock.zone()
    filters = EventFilter(
        search=search,
        actions=[a.value for a in actions_in(category)] if category else None,
        level=level,
        since=datetime.combine(since, time.min, tzinfo=zone) if since else None,
        until=datetime.combine(until + timedelta(days=1), time.min, tzinfo=zone) if until else None,
    )
    events, total = AuditRepository(session).page(company_id, filters, limit=limit, offset=offset)
    return AuditPage(
        items=[
            AuditEventView(
                id=e.id,
                occurred_at=e.occurred_at,
                actor_kind=e.actor_kind,
                actor_name=e.actor_name,
                action=e.action,
                level=e.level,
                subject_kind=e.subject_kind,
                subject_id=e.subject_id,
                subject_label=e.subject_label,
                summary=e.summary,
                details=e.details,
            )
            for e in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
