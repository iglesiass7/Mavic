"""Lo que ven las personas de la empresa: las llamadas de un caso (CU-11).

El operador abre un caso y ve qué pasó en cada llamada: en qué estado está, qué
ofertas recibió el agente (o escuchó el deudor, en el flujo anterior), el
resultado, el acuerdo (si lo hubo) y la transcripción.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.voice.infrastructure.orm import ConversationModel, PaymentAgreementModel
from mavic.modules.voice.infrastructure.repositories import (
    AgreementRepository,
    ConversationRepository,
)


@dataclass(frozen=True)
class AgreementView:
    offer_id: str
    modality: str
    currency: str
    original_amount: Decimal
    total_amount: Decimal
    installment_count: int
    installment_amount: Decimal | None
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    schedule: list[dict[str, Any]] | None  # solo el flujo anterior pactaba fechas
    created_at: datetime

    @classmethod
    def from_model(cls, agreement: PaymentAgreementModel) -> "AgreementView":
        return cls(
            offer_id=agreement.offer_id,
            modality=agreement.modality,
            currency=agreement.currency,
            original_amount=agreement.original_amount,
            total_amount=agreement.total_amount,
            installment_count=agreement.installment_count,
            installment_amount=agreement.installment_amount,
            discount_pct=agreement.discount_pct,
            discount_amount=agreement.discount_amount,
            schedule=agreement.schedule,
            created_at=agreement.created_at,
        )


@dataclass(frozen=True)
class ConversationView:
    id: uuid.UUID
    provider_conversation_id: str | None
    origin: str  # OUTBOUND (botón Llamar), TOOLS (flujo anterior), EXTERNAL
    status: str  # INITIATING, INITIATED, IN_PROGRESS, DONE, FAILED, NEEDS_REVIEW
    failure_reason: str | None
    review_reason: str | None
    started_at: datetime
    identity_verified: bool | None  # None: el flujo nuevo no verifica en Mavic
    offered: list[str]
    result: str | None
    unknown_count: int | None
    agreement: AgreementView | None
    summary: str | None
    call_duration_secs: int | None
    transcript: list[dict[str, Any]] | None


def list_case_conversations(
    session: Session, *, actor: Actor, clock: Clock, case_id: uuid.UUID
) -> list[ConversationView]:
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()
    # Verifica que el caso exista y sea de la empresa (si no, 404 CASE_NOT_FOUND).
    portfolio.case_detail(session, company_id=company_id, clock=clock, case_id=case_id)

    conversations = ConversationRepository(session).of_case(company_id, case_id)
    agreements = AgreementRepository(session).by_conversations([c.id for c in conversations])
    views = []
    for conversation in conversations:
        agreement = agreements.get(conversation.id)
        tools = conversation.origin == "TOOLS"
        views.append(
            ConversationView(
                id=conversation.id,
                provider_conversation_id=conversation.provider_conversation_id,
                origin=conversation.origin,
                status=conversation.status,
                failure_reason=conversation.failure_reason,
                review_reason=conversation.review_reason,
                started_at=conversation.created_at,
                identity_verified=conversation.identity_verified if tools else None,
                offered=_offered(conversation),
                result=conversation.result,
                unknown_count=conversation.unknown_count,
                agreement=AgreementView.from_model(agreement) if agreement else None,
                summary=conversation.summary,
                call_duration_secs=conversation.call_duration_secs,
                transcript=conversation.transcript,
            )
        )
    return views


def _offered(conversation: ConversationModel) -> list[str]:
    """Las ofertas de la llamada.

    - Llamada saliente: las que se le mandaron al agente, en orden.
    - Flujo anterior: las que el agente pidió (y por lo tanto dijo).
    """
    payload = conversation.initiation_payload or {}
    if conversation.origin == "OUTBOUND":
        return [str(offer["offer_id"]) for offer in payload.get("offers", [])]
    offered = []
    offers = conversation.offers or {}
    if conversation.single_payment_offered and offers.get("single_payment"):
        offered.append(offers["single_payment"]["offer_id"])
    if conversation.installments_offered and offers.get("installments"):
        offered.append(offers["installments"]["offer_id"])
    return offered
