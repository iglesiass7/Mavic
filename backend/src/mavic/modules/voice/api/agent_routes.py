"""Endpoints que llama el agente de ElevenLabs durante la llamada.

AUTENTICACIÓN: no hay cookie de sesión (el agente no es una persona). Cada
request trae el token secreto en el encabezado

    Authorization: Bearer <AGENT_TOOLS_TOKEN>

(ElevenLabs lo guarda como "Secret" en la configuración de cada herramienta.
En Swagger se prueba con el botón "Authorize".)
Sin token correcto: 401. Si el token no está configurado en Mavic: 503.

GET Y POST: cada herramienta acepta los parámetros por query string (GET) o
como JSON en el cuerpo (POST). Así funciona con cualquiera de las dos formas de
configurar una herramienta en ElevenLabs.

Las URLs usan los mismos nombres que las herramientas del agente.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mavic.api.deps import ClockDep, SessionDep, SettingsDep
from mavic.core.errors import AuthenticationError, ExternalServiceError
from mavic.modules.voice.api.agent_schemas import (
    ContextIn,
    ContextOut,
    InstallmentsOut,
    OfferIn,
    ResultIn,
    ResultOut,
    SinglePaymentOut,
)
from mavic.modules.voice.application import agent_tools

# Declara el esquema "Bearer" en la documentación OpenAPI. Así Swagger muestra
# el botón "Authorize" (candado) y manda el encabezado Authorization. Un campo
# común llamado "Authorization" no sirve: Swagger lo ignora a propósito.
_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="AgentToken",
    description="Token del agente de voz (AGENT_TOOLS_TOKEN). Pegá solo el token, sin 'Bearer'.",
)


def require_agent_token(
    settings: SettingsDep,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    expected = settings.agent_tools_token
    if expected is None:
        raise ExternalServiceError(
            "Las herramientas del agente están apagadas: falta AGENT_TOOLS_TOKEN en el .env.",
            service="agente de voz",
            retriable=False,
            code="AGENT_TOOLS_DISABLED",
        )
    if credentials is not None:
        received = credentials.credentials.strip()
    else:
        # También se acepta el token solo, sin la palabra "Bearer".
        received = request.headers.get("authorization", "").strip()
    # compare_digest: tarda lo mismo acierte o no, no da pistas a quien prueba tokens.
    if not received or not hmac.compare_digest(received, expected.get_secret_value()):
        raise AuthenticationError("Token del agente inválido.", code="AGENT_TOKEN_INVALID")


router = APIRouter(
    prefix="/agent/tools", tags=["agent"], dependencies=[Depends(require_agent_token)]
)


# ---------------------------------------------------------------- 1. contexto del caso


def _context(body: ContextIn, session: SessionDep, clock: ClockDep) -> ContextOut:
    context = agent_tools.get_case_context(
        session,
        clock=clock,
        case_reference=body.caso_id,
        provider_conversation_id=body.conversation_id,
        asked_name=body.nombre_consultado,
        answer=body.respuesta,
    )
    return ContextOut.from_context(context)


@router.post("/obtener_contexto_del_caso_v2")
def case_context(body: ContextIn, session: SessionDep, clock: ClockDep) -> ContextOut:
    """Verifica la identidad y, si se verificó, devuelve los datos de la deuda."""
    return _context(body, session, clock)


@router.get("/obtener_contexto_del_caso_v2")
def case_context_get(
    params: Annotated[ContextIn, Query()], session: SessionDep, clock: ClockDep
) -> ContextOut:
    return _context(params, session, clock)


# ---------------------------------------------------------------- 2. pago único


def _single(body: OfferIn, session: SessionDep, clock: ClockDep) -> SinglePaymentOut:
    answer = agent_tools.get_single_payment_offer(
        session,
        clock=clock,
        case_reference=body.caso_id,
        provider_conversation_id=body.conversation_id,
    )
    return SinglePaymentOut.from_answer(answer)


@router.post("/obtener_oferta_pago_unico_v2")
def single_payment(body: OfferIn, session: SessionDep, clock: ClockDep) -> SinglePaymentOut:
    """Oferta de pago único con descuento. Requiere identidad verificada."""
    return _single(body, session, clock)


@router.get("/obtener_oferta_pago_unico_v2")
def single_payment_get(
    params: Annotated[OfferIn, Query()], session: SessionDep, clock: ClockDep
) -> SinglePaymentOut:
    return _single(params, session, clock)


# ---------------------------------------------------------------- 3. cuotas


def _installments(body: OfferIn, session: SessionDep, clock: ClockDep) -> InstallmentsOut:
    answer = agent_tools.get_installments_offer(
        session,
        clock=clock,
        case_reference=body.caso_id,
        provider_conversation_id=body.conversation_id,
    )
    return InstallmentsOut.from_answer(answer)


@router.post("/obtener_oferta_cuotas_v2")
def installments(body: OfferIn, session: SessionDep, clock: ClockDep) -> InstallmentsOut:
    """Plan en cuotas. Requiere identidad verificada."""
    return _installments(body, session, clock)


@router.get("/obtener_oferta_cuotas_v2")
def installments_get(
    params: Annotated[OfferIn, Query()], session: SessionDep, clock: ClockDep
) -> InstallmentsOut:
    return _installments(params, session, clock)


# ---------------------------------------------------------------- 4. resultado


def _register(body: ResultIn, session: SessionDep, clock: ClockDep) -> ResultOut:
    answer = agent_tools.register_result(
        session,
        clock=clock,
        case_reference=body.caso_id,
        provider_conversation_id=body.conversation_id,
        result=body.resultado,
        offer_id=body.oferta_id,
        final_confirmation=body.confirmacion_final,
        unknown_count=body.cantidad_desconocimientos,
    )
    return ResultOut.from_answer(answer)


@router.post("/registrar_resultado_v2")
def register_result(body: ResultIn, session: SessionDep, clock: ClockDep) -> ResultOut:
    """Registra el resultado. Si no se puede, `registrado: false` y el `motivo`."""
    return _register(body, session, clock)


@router.get("/registrar_resultado_v2")
def register_result_get(
    params: Annotated[ResultIn, Query()], session: SessionDep, clock: ClockDep
) -> ResultOut:
    return _register(params, session, clock)
