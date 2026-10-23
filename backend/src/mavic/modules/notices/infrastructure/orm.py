"""Tablas de los avisos.

    companies 1 ──< notice_settings     (una fila por momento: preventivo, día de vencimiento)
    invoices  1 ──< notice_deliveries   (cada intento de mandar un aviso)

`notice_deliveries` es también el candado contra los duplicados: un índice único
PARCIAL deja una sola fila "mandando" o "mandado" por factura y momento. Si dos
procesos intentan avisar la misma factura a la vez (el botón y el envío
automático), el segundo choca con el índice y no manda nada.

    (factura, preventivo, SENDING)  ──> manda ──> SENT    el índice ya no deja otra
    (factura, preventivo, FAILED)   ──> se puede reintentar (el índice no cuenta los fallidos)
"""

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base, TimestampMixin

STAGES = "'preventive', 'due_today'"
CHANNELS = "'email', 'whatsapp'"


class NoticeSettingsModel(TimestampMixin, Base):
    __tablename__ = "notice_settings"
    __table_args__ = (
        CheckConstraint(f"stage IN ({STAGES})", name="stage_valid"),
        CheckConstraint(f"channel IN ({CHANNELS})", name="channel_valid"),
        CheckConstraint("days_before >= 0 AND days_before <= 30", name="days_before_valid"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), primary_key=True
    )
    stage: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    channel: Mapped[str] = mapped_column(String(10))
    send_time: Mapped[time] = mapped_column(Time)
    days_before: Mapped[int] = mapped_column(Integer)
    email_subject: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str] = mapped_column(Text, default="")
    whatsapp_template_sid: Mapped[str | None] = mapped_column(String(40))
    # El día (hora argentina) del último envío automático: corre una vez por día.
    last_auto_run_on: Mapped[date | None] = mapped_column(Date)


class NoticeDeliveryModel(Base):
    __tablename__ = "notice_deliveries"
    __table_args__ = (
        # Solo facturas de la misma empresa (la factura apunta a (id, company_id)).
        ForeignKeyConstraint(
            ["invoice_id", "company_id"],
            ["invoices.id", "invoices.company_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"stage IN ({STAGES})", name="stage_valid"),
        CheckConstraint(f"channel IN ({CHANNELS})", name="channel_valid"),
        CheckConstraint("status IN ('SENDING', 'SENT', 'FAILED')", name="status_valid"),
        CheckConstraint("trigger IN ('MANUAL', 'AUTOMATIC')", name="trigger_valid"),
        # Un aviso por factura y momento (los fallidos no cuentan: se pueden reintentar).
        Index(
            "uq_notice_deliveries_one_per_invoice_stage",
            "invoice_id",
            "stage",
            unique=True,
            postgresql_where=text("status IN ('SENDING', 'SENT')"),
        ),
        Index("ix_notice_deliveries_company_id_created_at", "company_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    invoice_id: Mapped[uuid.UUID] = mapped_column()
    stage: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(10))
    recipient: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(10))
    trigger: Mapped[str] = mapped_column(String(10))
    # Quién apretó el botón (vacío en los envíos automáticos).
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    # Lo que se mandó, para poder mostrarlo después (asunto y texto ya armados).
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
