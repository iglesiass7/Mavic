"""Webhook de ElevenLabs al terminar una llamada (`post_call_transcription`).

ElevenLabs manda la transcripción, un resumen y su análisis. En las llamadas que
inicia Mavic (ADR-034), el análisis trae además el RESULTADO de la llamada:

    data.analysis.data_collection_results.resultado.value   CONTACTADO | ACUERDO | ...
    data.analysis.data_collection_results.oferta_id.value   la oferta aceptada (si hubo acuerdo)

Orden de trabajo (para no perder nada):

    1. GUARDAR el envío tal como llegó (tabla webhook_events) y confirmar.
    2. PROCESAR en otra transacción: encontrar la llamada, guardar transcripción,
       validar el resultado contra la foto de ofertas y aplicar estado + acuerdo.

Cómo se encuentra la llamada:
    - por el conversation_id de ElevenLabs;
    - si todavía no está guardado (el webhook llegó antes), por el `caso_id` que
      viaja en las variables dinámicas;
    - si la llamada no la inició Mavic (por ejemplo, una prueba desde la consola
      de ElevenLabs con las variables cargadas a mano), se crea con origen EXTERNAL.

Qué se responde:
    - 200 si el envío quedó guardado (procesado, repetido o pendiente de revisión).
      Para ElevenLabs, cualquier otra respuesta es una falla, y con muchas fallas
      seguidas desactiva el webhook.
    - 401 si la firma no es válida; 422 si el cuerpo no es JSON.
    - 500 si falla la base al procesar: ElevenLabs reintenta y el envío guardado
      se procesa en el reintento.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import AuthenticationError, BusinessRuleViolationError, ConflictError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import ActorKind, AuditAction, Subject
from mavic.modules.negotiation.domain.offers import OfferKind
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.voice.application.payments import add_installments, payment_days_of
from mavic.modules.voice.domain.call_payload import (
    SCHEMA_VERSION,
    case_number_from_reference,
    find_snapshot_offer,
)
from mavic.modules.voice.domain.outcomes import (
    CASE_STATUS_FOR_RESULT,
    CallResult,
    ReviewReason,
    clean_offer_id,
    parse_result,
    review_reason_for,
)
from mavic.modules.voice.infrastructure.orm import (
    ConversationModel,
    PaymentAgreementModel,
    WebhookEventModel,
)
from mavic.modules.voice.infrastructure.repositories import (
    AgreementRepository,
    ConversationRepository,
    WebhookEventRepository,
)
from mavic.modules.voice.infrastructure.webhook_signature import is_valid_signature

logger = logging.getLogger(__name__)

TRANSCRIPTION_EVENT = "post_call_transcription"


@dataclass(frozen=True)
class SignedPayload:
    payload: dict[str, Any]
    body_sha256: str


@dataclass(frozen=True)
class WebhookOutcome:
    stored: bool
    reason: str | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _turns(transcript: Any) -> list[dict[str, Any]]:
    """Solo quién habló, qué dijo y en qué segundo. El resto (métricas internas,
    llamadas a herramientas) no hace falta para que una persona lea la llamada."""
    if not isinstance(transcript, list):
        return []
    return [
        {
            "role": turn.get("role"),
            "message": turn.get("message"),
            "time_in_call_secs": turn.get("time_in_call_secs"),
        }
        for turn in transcript
        if isinstance(turn, dict)
    ]


def _collected(analysis: dict[str, Any], key: str) -> object:
    """El valor de un dato recolectado por el agente: data_collection_results[key].value."""
    entry = _dict(analysis.get("data_collection_results")).get(key)
    return entry.get("value") if isinstance(entry, dict) else None


def _short(value: object, length: int) -> str | None:
    return str(value)[:length] if value else None


# ---------------------------------------------------------------- 1. guardar


def record_post_call(session: Session, *, clock: Clock, signed: SignedPayload) -> WebhookOutcome:
    payload = signed.payload
    data = _dict(payload.get("data"))
    provider_id = _short(data.get("conversation_id"), 100)

    events = WebhookEventRepository(session)
    event = events.store(
        WebhookEventModel(
            id=uuid.uuid4(),
            body_sha256=signed.body_sha256,
            event_type=str(payload.get("type") or "")[:60],
            provider_conversation_id=provider_id,
            payload=payload,
            received_at=clock.now(),
        )
    )
    if event.processed_at is not None:
        session.commit()
        return WebhookOutcome(stored=True, reason="YA_PROCESADO")
    event_id = event.id
    session.commit()  # el envío queda guardado pase lo que pase después

    # ------------------------------------------------------------ 2. procesar
    event_row = events.store(event)  # lo vuelve a leer, bloqueado
    if event_row.processed_at is not None:  # otro envío idéntico lo procesó mientras tanto
        session.commit()
        return WebhookOutcome(stored=True, reason="YA_PROCESADO")
    assert event_row.id == event_id  # noqa: S101

    outcome = _process(session, clock=clock, payload=payload, provider_id=provider_id)
    event_row.outcome = outcome.reason or "PROCESADO"
    if outcome.stored:
        event_row.processed_at = clock.now()
    # Si no se encontró la llamada, el envío queda guardado SIN procesar (pendiente).
    session.commit()
    return outcome


def _process(
    session: Session, *, clock: Clock, payload: dict[str, Any], provider_id: str | None
) -> WebhookOutcome:
    if payload.get("type") != TRANSCRIPTION_EVENT:
        logger.info("Webhook ignorado: tipo %s", payload.get("type"))
        return WebhookOutcome(stored=True, reason="EVENTO_NO_USADO")

    data = _dict(payload.get("data"))
    conversation = _find_conversation(session, clock=clock, data=data, provider_id=provider_id)
    if conversation is None:
        logger.info("Webhook guardado sin procesar: llamada desconocida")
        return WebhookOutcome(stored=False, reason="CONVERSACION_DESCONOCIDA")

    already_applied = conversation.webhook_received_at is not None and conversation.status in {
        "DONE",
        "NEEDS_REVIEW",
    }
    _store_transcript(conversation, data, clock)
    if conversation.origin == "TOOLS":
        # Flujo anterior: el resultado ya lo registró la herramienta.
        conversation.status = "DONE"
        return WebhookOutcome(stored=True)
    if already_applied:
        return WebhookOutcome(stored=True, reason="YA_PROCESADO")
    review = _apply_result(session, conversation, _dict(data.get("analysis")), clock)
    return WebhookOutcome(stored=True, reason=review)


def _find_conversation(
    session: Session, *, clock: Clock, data: dict[str, Any], provider_id: str | None
) -> ConversationModel | None:
    conversations = ConversationRepository(session)
    if provider_id:
        found = conversations.by_provider_id(provider_id)
        if found is not None:
            return found

    # Respaldo: el caso que viaja en las variables de la llamada.
    variables = _dict(
        _dict(data.get("conversation_initiation_client_data")).get("dynamic_variables")
    )
    number = case_number_from_reference(str(variables.get("caso_id") or ""))
    ref = portfolio.find_case_by_number(session, number) if number is not None else None
    if ref is None:
        return None

    waiting = conversations.awaiting_webhook(ref.company_id, ref.id)
    if waiting is not None:
        waiting.provider_conversation_id = provider_id
        return waiting

    # La llamada no la inició Mavic: se registra igual, sin foto de ofertas.
    external = ConversationModel(
        company_id=ref.company_id,
        case_id=ref.id,
        provider_conversation_id=provider_id,
        origin="EXTERNAL",
        status="INITIATED",
        identity_verified=False,
        single_payment_offered=False,
        installments_offered=False,
        created_at=_started_at(data) or clock.now(),
    )
    conversations.add(external)
    session.flush()
    return external


def _started_at(data: dict[str, Any]) -> datetime | None:
    start = _dict(data.get("metadata")).get("start_time_unix_secs")
    return datetime.fromtimestamp(start, tz=UTC) if isinstance(start, int) else None


def _store_transcript(conversation: ConversationModel, data: dict[str, Any], clock: Clock) -> None:
    metadata, analysis = _dict(data.get("metadata")), _dict(data.get("analysis"))
    conversation.transcript = _turns(data.get("transcript"))
    conversation.summary = analysis.get("transcript_summary")
    duration = metadata.get("call_duration_secs")
    conversation.call_duration_secs = duration if isinstance(duration, int) else None
    conversation.termination_reason = _short(metadata.get("termination_reason"), 200)
    conversation.analysis = {
        "call_successful": analysis.get("call_successful"),
        "evaluation_criteria_results": analysis.get("evaluation_criteria_results"),
        "data_collection_results": analysis.get("data_collection_results"),
    }
    conversation.agent_version_id = _short(data.get("version_id"), 100)
    conversation.branch_id = conversation.branch_id or _short(data.get("branch_id"), 100)
    conversation.webhook_received_at = clock.now()


# ---------------------------------------------------------------- resultado


def _apply_result(
    session: Session, conversation: ConversationModel, analysis: dict[str, Any], clock: Clock
) -> str | None:
    """Aplica el resultado. Devuelve el motivo de revisión, o None si quedó aplicado."""
    result_raw = _collected(analysis, "resultado")
    offer_id = clean_offer_id(_collected(analysis, "oferta_id"))
    snapshot = _snapshot_offers(conversation)
    offered = None if snapshot is None else frozenset(o["offer_id"] for o in snapshot)

    result = parse_result(result_raw)
    reason = review_reason_for(result_raw, offer_id, offered)
    if reason is None:
        assert result is not None  # noqa: S101 - review_reason_for lo validó
        try:
            portfolio.record_call_outcome(
                session,
                company_id=conversation.company_id,
                case_id=conversation.case_id,
                status=CASE_STATUS_FOR_RESULT[result],
            )
        except ConflictError:
            reason = ReviewReason.CASO_NO_NEGOCIABLE

    conversation.result = result.value if result else None
    conversation.result_recorded_at = clock.now()
    brief = portfolio.case_briefs(
        session, company_id=conversation.company_id, case_ids={conversation.case_id}
    )[conversation.case_id]
    subject = Subject("case", str(conversation.case_id), f"Caso #{brief.number}")
    if reason is not None:
        conversation.status = "NEEDS_REVIEW"
        conversation.review_reason = reason.value
        conversation.accepted_offer_id = None  # nunca un acuerdo sin validar
        audit.record(
            session,
            company_id=conversation.company_id,
            actor_kind=ActorKind.AGENT,
            action=AuditAction.CALL_NEEDS_REVIEW,
            subject=subject,
            summary=f"La llamada a {brief.debtor_name} (caso #{brief.number}) quedó para "
            f"revisar: {REVIEW_TEXT.get(reason.value, reason.value)}",
            details={"resultado": str(result_raw), "oferta_id": offer_id},
        )
        return reason.value

    assert result is not None  # noqa: S101 - sin motivo de revisión hay resultado
    audit.record(
        session,
        company_id=conversation.company_id,
        actor_kind=ActorKind.AGENT,
        action=AuditAction.CALL_FINISHED,
        subject=subject,
        summary=f"Terminó la llamada a {brief.debtor_name} (caso #{brief.number}): "
        f"{RESULT_TEXT[result]}.",
        details={"duracion_segundos": conversation.call_duration_secs},
    )
    if result is CallResult.ACUERDO:
        assert snapshot is not None and offer_id is not None  # noqa: S101 - validado
        conversation.accepted_offer_id = offer_id
        agreement = _agreement(conversation, snapshot, offer_id, clock)
        AgreementRepository(session).add(agreement)
        add_installments(
            session,
            agreement,
            agreed_on=clock.today(),
            payment_days=payment_days_of(conversation),
        )
        audit.record(
            session,
            company_id=conversation.company_id,
            actor_kind=ActorKind.AGENT,
            action=AuditAction.AGREEMENT_CREATED,
            subject=subject,
            summary=f"Acuerdo de pago del caso #{brief.number}: {_terms_text(agreement)}.",
            details={
                "oferta": agreement.offer_id,
                "total": str(agreement.total_amount),
                "cuotas": agreement.installment_count,
            },
        )
    else:
        conversation.accepted_offer_id = None  # un oferta_id suelto no significa nada
    conversation.status = "DONE"
    return None


def _terms_text(agreement: PaymentAgreementModel) -> str:
    """ "pago único de ARS 53325.45" o "6 cuotas de ARS 57866.67 (total ARS 347200.02)"."""
    money = f"{agreement.currency} {agreement.total_amount}"
    if agreement.installment_count == 1:
        return f"pago único de {money}"
    each = f"{agreement.currency} {agreement.installment_amount}"
    return f"{agreement.installment_count} cuotas de {each} (total {money})"


RESULT_TEXT: dict[CallResult, str] = {
    CallResult.CONTACTADO: "habló con el deudor, sin acuerdo",
    CallResult.ACUERDO: "acuerdo de pago",
    CallResult.DESCONOCIMIENTO: "el deudor no reconoce la deuda",
    CallResult.DERIVACION_HUMANA: "pidió hablar con una persona",
}

REVIEW_TEXT: dict[str, str] = {
    "SIN_RESULTADO": "el agente no informó un resultado.",
    "RESULTADO_INVALIDO": "el agente informó un resultado que no existe.",
    "ACUERDO_SIN_OFERTA": "acuerdo sin decir qué oferta.",
    "OFERTA_DESCONOCIDA": "acuerdo con una oferta que no se le dio.",
    "ACUERDO_SIN_FOTO": "la llamada no se inició desde Mavic; el acuerdo no se puede validar.",
    "CASO_NO_NEGOCIABLE": "el caso ya tenía un resultado de otra llamada.",
}


def _snapshot_offers(conversation: ConversationModel) -> list[dict[str, Any]] | None:
    payload = conversation.initiation_payload or {}
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    offers = payload.get("offers")
    return offers if isinstance(offers, list) else None


def _agreement(
    conversation: ConversationModel, snapshot: list[dict[str, Any]], offer_id: str, clock: Clock
) -> PaymentAgreementModel:
    """El acuerdo con los números de la FOTO, nunca del texto de la llamada."""
    offer = find_snapshot_offer(snapshot, offer_id)
    assert offer is not None  # noqa: S101 - validado contra la foto
    payload = conversation.initiation_payload or {}
    return PaymentAgreementModel(
        company_id=conversation.company_id,
        case_id=conversation.case_id,
        conversation_id=conversation.id,
        offer_id=offer.offer_id,
        modality=offer.kind.value,
        currency=str(payload["currency"]),
        original_amount=Decimal(str(payload["total_amount"])),
        total_amount=offer.total_amount,
        installment_count=offer.installment_count,
        installment_amount=offer.installment_amount
        if offer.kind is OfferKind.INSTALLMENTS
        else None,
        discount_pct=offer.discount_pct,
        discount_amount=offer.discount_amount,
        schedule=None,
        created_at=clock.now(),
    )


# ---------------------------------------------------------------- firma


def parse_signed_payload(
    *, signature_header: str | None, body: bytes, secret: str, clock: Clock
) -> SignedPayload:
    """Verifica la firma de ElevenLabs y devuelve el JSON. Sin firma válida: 401."""
    now = int(clock.now().timestamp())
    if not is_valid_signature(signature_header, body, secret, now):
        raise AuthenticationError("Firma del webhook inválida o vencida.", code="INVALID_SIGNATURE")
    try:
        payload = json.loads(body)
    except ValueError as error:
        raise BusinessRuleViolationError("El cuerpo no es JSON.", code="INVALID_JSON") from error
    if not isinstance(payload, dict):
        raise BusinessRuleViolationError("El cuerpo no es un objeto JSON.", code="INVALID_JSON")
    return SignedPayload(payload=payload, body_sha256=hashlib.sha256(body).hexdigest())
