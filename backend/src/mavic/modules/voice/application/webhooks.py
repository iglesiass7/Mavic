"""Webhook de ElevenLabs al terminar una llamada (`post_call_transcription`).

ElevenLabs manda la transcripción, un resumen y su análisis (criterios de
evaluación y datos recolectados). Se guardan en la conversación que ya crearon
las herramientas durante la llamada.

La firma del mensaje se verifica primero (`parse_signed_payload`).

Qué se responde siempre 200, aunque se ignore el mensaje: para ElevenLabs,
cualquier otra respuesta es una falla, y con muchas fallas seguidas desactiva
el webhook. Se ignoran (y se registra en el log):
- tipos de evento que no usamos (por ejemplo, el audio);
- llamadas que nunca usaron una herramienta (no sabemos de qué caso son).
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import AuthenticationError, BusinessRuleViolationError
from mavic.modules.voice.infrastructure.repositories import ConversationRepository
from mavic.modules.voice.infrastructure.webhook_signature import is_valid_signature

logger = logging.getLogger(__name__)

TRANSCRIPTION_EVENT = "post_call_transcription"


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


def record_post_call(session: Session, *, clock: Clock, payload: dict[str, Any]) -> WebhookOutcome:
    if payload.get("type") != TRANSCRIPTION_EVENT:
        logger.info("Webhook ignorado: tipo %s", payload.get("type"))
        return WebhookOutcome(stored=False, reason="EVENTO_NO_USADO")

    data = _dict(payload.get("data"))
    provider_id = str(data.get("conversation_id") or "")
    conversation = (
        ConversationRepository(session).by_provider_id(provider_id) if provider_id else None
    )
    if conversation is None:
        logger.info("Webhook ignorado: conversación desconocida")
        return WebhookOutcome(stored=False, reason="CONVERSACION_DESCONOCIDA")

    metadata, analysis = _dict(data.get("metadata")), _dict(data.get("analysis"))
    conversation.transcript = _turns(data.get("transcript"))
    conversation.summary = analysis.get("transcript_summary")
    duration = metadata.get("call_duration_secs")
    conversation.call_duration_secs = duration if isinstance(duration, int) else None
    reason = metadata.get("termination_reason")
    conversation.termination_reason = str(reason)[:200] if reason else None
    conversation.analysis = {
        "call_successful": analysis.get("call_successful"),
        "evaluation_criteria_results": analysis.get("evaluation_criteria_results"),
        "data_collection_results": analysis.get("data_collection_results"),
    }
    conversation.webhook_received_at = clock.now()
    session.commit()
    return WebhookOutcome(stored=True)


def parse_signed_payload(
    *, signature_header: str | None, body: bytes, secret: str, clock: Clock
) -> dict[str, Any]:
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
    return payload
