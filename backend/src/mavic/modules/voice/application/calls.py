"""Caso de uso: llamar al deudor con el agente (botón "Llamar", ADR-034).

    1. PREPARAR   caso negociable, sin otra llamada en curso, con regla y ofertas
    2. FOTO       se arman las 8 variables y se guarda la conversación INITIATING
                  (existe ANTES de pedir la llamada: si ElevenLabs falla, queda registro)
    3. INICIAR    ElevenLabs llama por Twilio y devuelve conversation_id y callSid
    4. GUARDAR    INITIATED con esos ids  —o—  FAILED con el motivo

El resultado de la llamada NO se conoce acá: llega después, en el webhook
(application/webhooks.py), y se valida contra la foto del paso 2.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import BusinessRuleViolationError, ConflictError, ExternalServiceError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditAction, Subject
from mavic.modules.identity.application.companies import company_name
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.negotiation.application.offers import call_offers_for_case
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.portfolio.domain.cases import is_negotiable
from mavic.modules.voice.domain.call_gateway import CallGateway, CallGatewayError
from mavic.modules.voice.domain.call_payload import (
    SCHEMA_VERSION,
    CallPayloadError,
    DebtLine,
    build_dynamic_variables,
    offers_snapshot,
)
from mavic.modules.voice.infrastructure.orm import ConversationModel
from mavic.modules.voice.infrastructure.repositories import ConversationRepository

# Una llamada iniciada que no terminó (no llegó su webhook) bloquea otra llamada
# al mismo caso durante este tiempo. Pasado ese tiempo se asume que se perdió.
ACTIVE_CALL_WINDOW = timedelta(minutes=30)
SERVICE = "agente de voz"


@dataclass(frozen=True)
class CallSettings:
    """La parte de la configuración que usa una llamada (viene de core/config.py)."""

    agent_id: str
    branch_id: str | None


@dataclass(frozen=True)
class StartedCall:
    conversation_id: uuid.UUID  # el id de Mavic
    status: str
    provider_conversation_id: str | None
    provider_call_sid: str | None


def start_debt_call(
    session: Session,
    *,
    actor: Actor,
    clock: Clock,
    gateway: CallGateway | None,
    call_settings: CallSettings | None,
    case_id: uuid.UUID,
) -> StartedCall:
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()
    if gateway is None or call_settings is None:
        raise ExternalServiceError(
            "Las llamadas están apagadas: faltan ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID o "
            "ELEVENLABS_PHONE_NUMBER_ID en el .env.",
            service=SERVICE,
            retriable=False,
            code="CALLS_DISABLED",
        )

    # 1. PREPARAR, con el caso bloqueado: dos clics a la vez no generan dos llamadas.
    portfolio.lock_case(session, company_id=company_id, case_id=case_id)
    detail = portfolio.case_detail(session, company_id=company_id, clock=clock, case_id=case_id)
    summary = detail.summary
    if not is_negotiable(summary.status):
        raise ConflictError(
            "El caso ya tiene un resultado: no se vuelve a llamar.", code="CASE_NOT_NEGOTIABLE"
        )
    conversations = ConversationRepository(session)
    if conversations.has_active_call(company_id, case_id, since=clock.now() - ACTIVE_CALL_WINDOW):
        raise ConflictError(
            "Ya hay una llamada en curso para este caso. Esperá a que termine.",
            code="CALL_IN_PROGRESS",
        )
    offers = call_offers_for_case(session, company_id=company_id, clock=clock, case_id=case_id)
    if not offers.offers:
        raise ConflictError(
            "Ninguna regla activa se aplica a este caso: no hay ofertas para llamar.",
            code="NO_MATCHING_RULE",
        )

    # 2. FOTO de lo que recibe el agente.
    try:
        variables = build_dynamic_variables(
            case_number=summary.number,
            debtor_name=summary.debtor.name,
            creditor_name=company_name(session, company_id),
            currency=summary.currency,
            debts=[
                DebtLine(i.external_id, i.description, i.amount, i.currency)
                for i in detail.invoices
            ],
            offers=offers.offers,
        )
    except CallPayloadError as exc:
        raise BusinessRuleViolationError(str(exc), code=exc.code) from exc

    assert offers.rule is not None  # noqa: S101 - hay ofertas, hay regla
    conversation = ConversationModel(
        company_id=company_id,
        case_id=case_id,
        origin="OUTBOUND",
        status="INITIATING",
        branch_id=call_settings.branch_id,
        initiation_payload={
            "schema_version": SCHEMA_VERSION,
            "agent_id": call_settings.agent_id,
            "branch_id": call_settings.branch_id,
            "to_number": summary.debtor.phone,
            "currency": summary.currency,
            "total_amount": str(summary.total_amount),
            "rule": {
                "id": str(offers.rule.id),
                "name": offers.rule.name,
                "payment_days": offers.rule.payment_days,
            },
            "dynamic_variables": variables,
            "offers": offers_snapshot(offers.offers),
        },
        identity_verified=False,
        single_payment_offered=False,
        installments_offered=False,
        created_at=clock.now(),
    )
    conversations.add(conversation)
    subject = Subject("case", str(case_id), f"Caso #{summary.number}")
    audit.record(
        session,
        company_id=company_id,
        actor=actor,
        action=AuditAction.CALL_STARTED,
        subject=subject,
        summary=f"Pidió llamar a {summary.debtor.name} (caso #{summary.number}) con la regla "
        f"'{offers.rule.name}'.",
        details={"ofertas": [offer.offer_id for offer in offers.offers]},
    )
    session.commit()  # la fila existe antes de llamar (y se libera el bloqueo del caso)

    # 3. INICIAR.
    try:
        result = gateway.start_call(
            to_number=summary.debtor.phone,
            dynamic_variables=variables,
            branch_id=call_settings.branch_id,
        )
    except CallGatewayError as exc:
        _fail(session, conversation.id, str(exc), actor=actor, subject=subject)
        raise ExternalServiceError(
            f"ElevenLabs no pudo iniciar la llamada ({exc}).",
            service=SERVICE,
            code="CALL_NOT_STARTED",
        ) from exc
    if not result.accepted or not result.conversation_id:
        reason = result.message or "ElevenLabs no aceptó la llamada."
        _fail(session, conversation.id, reason, actor=actor, subject=subject)
        raise ExternalServiceError(
            f"ElevenLabs no pudo iniciar la llamada ({reason}).",
            service=SERVICE,
            code="CALL_NOT_STARTED",
        )

    # 4. GUARDAR los ids. El webhook pudo llegar antes y ya haberla encontrado
    # por el caso: en ese caso no se pisa lo que hizo.
    saved = conversations.get_for_update(conversation.id)
    assert saved is not None  # noqa: S101 - se creó arriba
    if saved.provider_conversation_id is None:
        saved.provider_conversation_id = result.conversation_id
    saved.provider_call_sid = result.call_sid
    if saved.status == "INITIATING":
        saved.status = "INITIATED"
    session.commit()
    return StartedCall(
        conversation_id=saved.id,
        status=saved.status,
        provider_conversation_id=saved.provider_conversation_id,
        provider_call_sid=saved.provider_call_sid,
    )


def _fail(
    session: Session, conversation_id: uuid.UUID, reason: str, *, actor: Actor, subject: Subject
) -> None:
    session.rollback()
    conversation = ConversationRepository(session).get_for_update(conversation_id)
    if conversation is not None and conversation.status == "INITIATING":
        conversation.status = "FAILED"
        conversation.failure_reason = reason[:1000]
        audit.record(
            session,
            company_id=conversation.company_id,
            actor=actor,
            action=AuditAction.CALL_FAILED,
            subject=subject,
            summary=f"La llamada del {subject.label.lower()} no se pudo iniciar: {reason}",
        )
    session.commit()
