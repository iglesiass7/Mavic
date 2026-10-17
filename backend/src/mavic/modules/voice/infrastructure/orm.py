"""Tablas del agente de voz.

    cases 1 ──< conversations 1 ──o payment_agreements
              (una por llamada)     (si la llamada terminó en acuerdo)

- `conversations`: una fila por llamada, identificada por el id que le da
  ElevenLabs. Guarda lo que pasó durante la llamada (identidad, ofertas
  presentadas, resultado) y, cuando llega el webhook, la transcripción.
- `payment_agreements`: el acuerdo con sus números FIJOS (montos y cronograma
  de cuotas tal como se ofrecieron). Aunque después cambien las reglas, el
  acuerdo dice lo que se acordó.

Igual que en la cartera, las claves foráneas compuestas (case_id, company_id)
impiden que una llamada o un acuerdo queden asociados a un caso de otra empresa.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base, TimestampMixin

_RESULTS = "'CONTACTADO', 'DESCONOCIMIENTO', 'ACUERDO', 'DERIVACION_HUMANA'"


class ConversationModel(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"], ["cases.id", "cases.company_id"], ondelete="RESTRICT"
        ),
        CheckConstraint(f"result IS NULL OR result IN ({_RESULTS})", name="result_valid"),
        CheckConstraint("unknown_count IS NULL OR unknown_count >= 0", name="unknown_count_valid"),
        Index("ix_conversations_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    case_id: Mapped[uuid.UUID] = mapped_column()
    # El id de la conversación en ElevenLabs. Único: si la misma llamada usa
    # varias herramientas, todas caen en la misma fila.
    provider_conversation_id: Mapped[str] = mapped_column(String(100), unique=True)

    # Durante la llamada (lo escriben las herramientas del agente).
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    offers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # foto de las ofertas
    single_payment_offered: Mapped[bool] = mapped_column(Boolean, default=False)
    installments_offered: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str | None] = mapped_column(String(30))
    accepted_offer_id: Mapped[str | None] = mapped_column(String(40))
    final_confirmation: Mapped[bool | None] = mapped_column(Boolean)
    unknown_count: Mapped[int | None] = mapped_column(Integer)
    result_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Después de la llamada (lo escribe el webhook de ElevenLabs).
    transcript: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    call_duration_secs: Mapped[int | None] = mapped_column(Integer)
    termination_reason: Mapped[str | None] = mapped_column(String(200))
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    webhook_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentAgreementModel(Base):
    __tablename__ = "payment_agreements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"], ["cases.id", "cases.company_id"], ondelete="RESTRICT"
        ),
        CheckConstraint("modality IN ('PAGO_UNICO', 'CUOTAS')", name="modality_valid"),
        CheckConstraint("total_amount > 0", name="total_amount_positive"),
        CheckConstraint("installment_count >= 1", name="installment_count_valid"),
        Index("ix_payment_agreements_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    case_id: Mapped[uuid.UUID] = mapped_column()
    # Una llamada genera como máximo un acuerdo.
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), unique=True
    )
    offer_id: Mapped[str] = mapped_column(String(40))
    modality: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    installment_count: Mapped[int] = mapped_column(Integer)
    # [{"number": 1, "due_date": "2026-10-21", "amount": "40000.00"}, ...]
    schedule: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
