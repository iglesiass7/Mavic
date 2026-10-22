"""Iniciar una llamada saliente con el SDK oficial de ElevenLabs (por Twilio).

Es la ÚNICA parte de Mavic que conoce el SDK. Cumple la interfaz
`CallGateway` (domain/call_gateway.py): en los tests se reemplaza por una falsa
y no se llama a nadie.

    Mavic ──outbound_call──► ElevenLabs ──► Twilio ──► teléfono del deudor
            (variables)          │
                                 └── devuelve conversation_id y callSid
"""

import logging
from typing import Any

import httpx

from mavic.modules.voice.domain.call_gateway import CallGatewayError, OutboundCallResult

logger = logging.getLogger(__name__)


class ElevenLabsCallGateway:
    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        phone_number_id: str,
        http_client: httpx.Client | None = None,  # los tests pasan uno falso
    ) -> None:
        from elevenlabs.client import ElevenLabs  # noqa: PLC0415 - solo si hay llamadas

        self._client = ElevenLabs(api_key=api_key, timeout=30, httpx_client=http_client)
        self._agent_id = agent_id
        self._phone_number_id = phone_number_id

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def start_call(
        self, *, to_number: str, dynamic_variables: dict[str, Any], branch_id: str | None
    ) -> OutboundCallResult:
        client_data: dict[str, Any] = {"dynamic_variables": dynamic_variables}
        if branch_id:
            client_data["branch_id"] = branch_id
        try:
            response = self._client.conversational_ai.twilio.outbound_call(
                agent_id=self._agent_id,
                agent_phone_number_id=self._phone_number_id,
                to_number=to_number,
                conversation_initiation_client_data=client_data,
            )
        except Exception as exc:  # el SDK lanza tipos variados (HTTP, red, validación)
            # Nunca se loguea la clave: el mensaje del SDK no la incluye.
            logger.warning("ElevenLabs no inició la llamada: %s", type(exc).__name__)
            raise CallGatewayError(_readable(exc)) from exc
        return OutboundCallResult(
            accepted=bool(response.success),
            message=str(response.message or ""),
            conversation_id=response.conversation_id,
            call_sid=response.call_sid,
        )


def _readable(exc: Exception) -> str:
    """Un motivo que una persona entienda, sin datos sensibles.

    >>> _readable(httpx.ConnectError("boom"))
    'sin conexión con ElevenLabs (ConnectError)'
    """
    status = getattr(exc, "status_code", None)
    if not status:
        return f"sin conexión con ElevenLabs ({type(exc).__name__})"
    body = getattr(exc, "body", None)
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):  # ElevenLabs suele mandar {"status": ..., "message": ...}
        detail = detail.get("message")
    return f"HTTP {status}: {detail if isinstance(detail, str) else 'error de ElevenLabs'}"
