"""Tablas del agente de voz.

    cases 1 ──< conversations 1 ──o payment_agreements 1 ──< agreement_installments
              (una por llamada)     (si la llamada         (las cuotas, con fecha
                                     terminó en acuerdo)     y si se pagaron)

- `conversations`: una fila por llamada. Hay dos formas de que nazca:
    * LLAMADA SALIENTE (ADR-034): Mavic crea la fila ANTES de pedirle a
      ElevenLabs que llame, con la foto exacta de lo que le manda al agente
      (`initiation_payload`). El resultado llega en el webhook.
    * HERRAMIENTAS (flujo anterior): la crea la primera herramienta que usa el
      agente durante la llamada.
  Cuando llega el webhook, se completa con la transcripción y el análisis.
- `payment_agreements`: el acuerdo con sus números FIJOS, copiados de la oferta
  que escuchó el deudor. Aunque después cambien las reglas, el acuerdo dice lo
  que se acordó.
- `agreement_installments`: las cuotas del acuerdo (un pago único es una
  cuota). Una persona de la empresa marca cada una como pagada.
- `webhook_events`: cada aviso de fin de llamada TAL COMO LLEGÓ, guardado antes
  de procesarlo. Si algo falla al procesarlo, no se pierde nada.

Igual que en la cartera, las claves foráneas compuestas (case_id, company_id)
impiden que una llamada o un acuerdo queden asociados a un caso de otra empresa.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base, TimestampMixin

_RESULTS = "'CONTACTADO', 'DESCONOCIMIENTO', 'ACUERDO', 'DERIVACION_HUMANA'"
_STATUSES = "'INITIATING', 'INITIATED', 'IN_PROGRESS', 'DONE', 'FAILED', 'NEEDS_REVIEW'"
_ORIGINS = "'OUTBOUND', 'TOOLS', 'EXTERNAL'"


class ConversationModel(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "company_id"], ["cases.id", "cases.company_id"], ondelete="RESTRICT"
        ),
        CheckConstraint(f"result IS NULL OR result IN ({_RESULTS})", name="result_valid"),
        CheckConstraint("unknown_count IS NULL OR unknown_count >= 0", name="unknown_count_valid"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),
        CheckConstraint(f"origin IN ({_ORIGINS})", name="origin_valid"),
        Index("ix_conversations_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    case_id: Mapped[uuid.UUID] = mapped_column()
    # El id de la conversación en ElevenLabs. Único cuando existe. En una
    # llamada saliente se conoce recién cuando ElevenLabs acepta la llamada.
    provider_conversation_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    # El id de la llamada en Twilio (para soporte y para cruzar con Twilio).
    provider_call_sid: Mapped[str | None] = mapped_column(String(64), unique=True)

    # De dónde salió la fila (OUTBOUND, TOOLS, EXTERNAL) y en qué estado está:
    #   INITIATING   creada, ElevenLabs todavía no respondió
    #   INITIATED    ElevenLabs aceptó la llamada (ya hay conversation_id)
    #   IN_PROGRESS  el agente está usando herramientas (flujo anterior)
    #   DONE         llegó el webhook y se aplicó el resultado
    #   FAILED       no se pudo iniciar la llamada (ver failure_reason)
    #   NEEDS_REVIEW llegó el webhook pero sus datos no alcanzan: lo revisa una persona
    origin: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    branch_id: Mapped[str | None] = mapped_column(String(100))  # rama del agente usada
    agent_version_id: Mapped[str | None] = mapped_column(String(100))  # la informa el webhook
    # Llamada saliente: lo que se le mandó al agente, exacto (variables, ofertas, versión).
    initiation_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    review_reason: Mapped[str | None] = mapped_column(String(60))

    # Durante la llamada, en el flujo anterior (lo escriben las herramientas).
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
        CheckConstraint(
            "modality <> 'CUOTAS' OR installment_amount IS NOT NULL",
            name="installments_have_amount",
        ),
        Index("ix_payment_agreements_case_id", "case_id"),
        # Para que las cuotas apunten a (id, company_id): nunca a un acuerdo de otra empresa.
        UniqueConstraint("id", "company_id"),
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
    installment_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # cada cuota
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Solo el flujo anterior pactaba fechas:
    # [{"number": 1, "due_date": "2026-10-21", "amount": "40000.00"}, ...]
    # En las llamadas salientes el agente no acuerda fechas: queda vacío.
    schedule: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgreementInstallmentModel(Base):
    """Una cuota de un acuerdo. `paid_on` vacío = todavía no se pagó."""

    __tablename__ = "agreement_installments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agreement_id", "company_id"],
            ["payment_agreements.id", "payment_agreements.company_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("agreement_id", "number"),
        CheckConstraint("number >= 1", name="number_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        # Pagada = tiene fecha de pago Y quién y cuándo lo registró (todo o nada).
        CheckConstraint(
            "(paid_on IS NULL) = (paid_recorded_at IS NULL)", name="paid_fields_together"
        ),
        Index("ix_agreement_installments_company_id_due_date", "company_id", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    agreement_id: Mapped[uuid.UUID] = mapped_column()
    number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_on: Mapped[date | None] = mapped_column(Date)  # el día que pagó el deudor
    paid_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(String(300))


class WebhookEventModel(Base):
    """Bandeja de entrada de los webhooks: se guarda primero, se procesa después.

    `body_sha256` hace que el mismo envío repetido (ElevenLabs reintenta) se
    reconozca: no se guarda dos veces ni se aplica dos veces.
    """

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    body_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(60))
    provider_conversation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Qué se hizo: STORED, IGNORED_EVENT, UNMATCHED, NEEDS_REVIEW, ...
    outcome: Mapped[str | None] = mapped_column(String(40))
