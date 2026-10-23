"""Tabla de la auditoría: un evento por fila, solo se agrega.

`seq` ordena los eventos: dentro de una misma transacción, `occurred_at` es el
mismo para todos (es la hora de inicio de la transacción), y `seq` desempata.

El nombre de quien lo hizo se guarda tal como era ese día (`actor_name`): si
mañana la persona cambia de nombre, el registro de ayer no cambia.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DDL,
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_company_id_seq", "company_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    # None: eventos de la plataforma que no son de ninguna empresa.
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    actor_kind: Mapped[str] = mapped_column(String(10))
    # Sin clave foránea a propósito: registrar un evento nunca debe hacer fallar
    # la operación que lo genera. El nombre ya queda guardado en `actor_name`.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    actor_name: Mapped[str] = mapped_column(String(120))

    action: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(10))
    subject_kind: Mapped[str | None] = mapped_column(String(20))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    subject_label: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


# La base no deja cambiar ni borrar eventos: ni la app, ni alguien con acceso a
# la base por error. Lo mismo está en la migración; esto es para las bases que se
# crean desde los modelos (los tests).
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events solo admite agregar filas (no se edita ni se borra)';
END;
$$ LANGUAGE plpgsql
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
"""

event.listen(AuditEventModel.__table__, "after_create", DDL(APPEND_ONLY_FUNCTION))  # type: ignore[no-untyped-call]
event.listen(AuditEventModel.__table__, "after_create", DDL(APPEND_ONLY_TRIGGER))  # type: ignore[no-untyped-call]
