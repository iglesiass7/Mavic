"""Webhook de fin de llamada de ElevenLabs.

Se autentica con la FIRMA del mensaje (ver infrastructure/webhook_signature.py),
no con sesión ni token: así lo hace ElevenLabs.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from mavic.api.deps import ClockDep, SessionDep, SettingsDep
from mavic.core.errors import ExternalServiceError
from mavic.modules.voice.application import webhooks

router = APIRouter(tags=["agent"])


async def signed_payload(
    request: Request, settings: SettingsDep, clock: ClockDep
) -> dict[str, Any]:
    """Lee el cuerpo EXACTO (la firma se calcula sobre esos bytes) y lo verifica."""
    secret = settings.elevenlabs_webhook_secret
    if secret is None:
        raise ExternalServiceError(
            "El webhook está apagado: falta ELEVENLABS_WEBHOOK_SECRET en el .env.",
            service="agente de voz",
            retriable=False,
            code="WEBHOOK_DISABLED",
        )
    return webhooks.parse_signed_payload(
        signature_header=request.headers.get("elevenlabs-signature"),
        body=await request.body(),
        secret=secret.get_secret_value(),
        clock=clock,
    )


@router.post("/webhooks/elevenlabs")
def elevenlabs_webhook(
    payload: Annotated[dict[str, Any], Depends(signed_payload)],
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    """Guarda la transcripción y el análisis de la llamada. Responde 200 aunque la ignore."""
    outcome = webhooks.record_post_call(session, clock=clock, payload=payload)
    return {"stored": outcome.stored, "reason": outcome.reason}
