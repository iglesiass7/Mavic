"""Resultados de una llamada y reglas para registrarlos.

El agente registra uno de cuatro resultados (los nombres son los del agente):

    resultado           ->  estado del caso
    CONTACTADO          ->  contactado      (habló, sin acuerdo todavía)
    ACUERDO             ->  acuerdo         (aceptó una oferta)
    DESCONOCIMIENTO     ->  en disputa      (no reconoce la deuda)
    DERIVACION_HUMANA   ->  derivado        (lo tiene que atender una persona)

Lo que más importa proteger es el ACUERDO: es un compromiso de pago. Se
registra SOLO si se cumplen las tres condiciones:
  1. la identidad se verificó en esa llamada;
  2. la persona confirmó al final (`confirmacion_final = true`);
  3. la oferta aceptada es una que el backend le dio EN ESA LLAMADA.
La tercera evita que una "oferta" inventada por la IA quede como acuerdo.
"""

from enum import StrEnum

from mavic.modules.portfolio.domain.cases import CaseStatus


class CallResult(StrEnum):
    CONTACTADO = "CONTACTADO"
    DESCONOCIMIENTO = "DESCONOCIMIENTO"
    ACUERDO = "ACUERDO"
    DERIVACION_HUMANA = "DERIVACION_HUMANA"


CASE_STATUS_FOR_RESULT: dict[CallResult, CaseStatus] = {
    CallResult.CONTACTADO: CaseStatus.CONTACTED,
    CallResult.ACUERDO: CaseStatus.AGREEMENT,
    CallResult.DESCONOCIMIENTO: CaseStatus.DISPUTED,
    CallResult.DERIVACION_HUMANA: CaseStatus.ESCALATED,
}

# Resultados que solo tienen sentido si se habló con el titular: un acuerdo, o
# decir "no reconozco esta deuda", solo los puede hacer el deudor.
_NEED_IDENTITY = frozenset({CallResult.ACUERDO, CallResult.DESCONOCIMIENTO})


class Rejection(StrEnum):
    """Por qué no se registró un resultado. El agente lo recibe en `motivo`."""

    IDENTIDAD_NO_VERIFICADA = "IDENTIDAD_NO_VERIFICADA"
    ACUERDO_SIN_CONFIRMAR = "ACUERDO_SIN_CONFIRMAR"
    OFERTA_NO_OFRECIDA = "OFERTA_NO_OFRECIDA"
    CASO_NO_NEGOCIABLE = "CASO_NO_NEGOCIABLE"
    YA_REGISTRADO = "YA_REGISTRADO"


def check_registration(
    result: CallResult,
    *,
    identity_verified: bool,
    final_confirmation: bool,
    offer_id: str | None,
    offered_ids: frozenset[str],
) -> Rejection | None:
    """None si se puede registrar; si no, el motivo.

    >>> check_registration(CallResult.ACUERDO, identity_verified=True,
    ...     final_confirmation=True, offer_id="PAGO-UNICO", offered_ids=frozenset())
    <Rejection.OFERTA_NO_OFRECIDA: 'OFERTA_NO_OFRECIDA'>
    """
    if result in _NEED_IDENTITY and not identity_verified:
        return Rejection.IDENTIDAD_NO_VERIFICADA
    if result is CallResult.ACUERDO:
        if not final_confirmation:
            return Rejection.ACUERDO_SIN_CONFIRMAR
        if offer_id not in offered_ids:
            return Rejection.OFERTA_NO_OFRECIDA
    return None


# ---------------------------------------------------------------- llamadas salientes (ADR-034)
#
# En las llamadas salientes el agente no registra nada durante la llamada: el
# resultado llega en el webhook, dentro del análisis de ElevenLabs
# (data_collection_results.resultado y .oferta_id). Mavic lo valida contra la
# foto de las ofertas que le mandó al agente al iniciar.


class ReviewReason(StrEnum):
    """Por qué un webhook no se pudo aplicar solo y lo tiene que revisar una persona."""

    SIN_RESULTADO = "SIN_RESULTADO"  # el análisis no trae `resultado`
    RESULTADO_INVALIDO = "RESULTADO_INVALIDO"  # trae un valor que no es de los cuatro
    ACUERDO_SIN_OFERTA = "ACUERDO_SIN_OFERTA"  # ACUERDO sin oferta_id
    OFERTA_DESCONOCIDA = "OFERTA_DESCONOCIDA"  # oferta_id que no se le mandó al agente
    ACUERDO_SIN_FOTO = "ACUERDO_SIN_FOTO"  # llamada iniciada fuera de Mavic: no hay foto
    CASO_NO_NEGOCIABLE = "CASO_NO_NEGOCIABLE"  # el caso ya tenía un resultado


def parse_result(raw: object) -> CallResult | None:
    """El resultado informado, sin importar mayúsculas ni espacios. None si no es válido.

    >>> parse_result(" acuerdo "), parse_result("TAL VEZ"), parse_result(None)
    (<CallResult.ACUERDO: 'ACUERDO'>, None, None)
    """
    if not isinstance(raw, str):
        return None
    try:
        return CallResult(raw.strip().upper())
    except ValueError:
        return None


def clean_offer_id(raw: object) -> str | None:
    """El id de oferta sin espacios; vacío cuenta como "no vino".

    >>> clean_offer_id(" PAGO-UNICO "), clean_offer_id(""), clean_offer_id(None)
    ('PAGO-UNICO', None, None)
    """
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def review_reason_for(
    result_raw: object, offer_id: str | None, offered_ids: frozenset[str] | None
) -> ReviewReason | None:
    """None si el resultado se puede aplicar; si no, por qué va a revisión.

    `offered_ids` son las ofertas de la foto de la llamada (None si la llamada
    no la inició Mavic y no hay foto).

    >>> review_reason_for("ACUERDO", "OF-9", frozenset({"PAGO-UNICO"}))
    <ReviewReason.OFERTA_DESCONOCIDA: 'OFERTA_DESCONOCIDA'>
    >>> review_reason_for("CONTACTADO", "OF-9", None) is None
    True
    """
    if result_raw is None or (isinstance(result_raw, str) and not result_raw.strip()):
        return ReviewReason.SIN_RESULTADO
    result = parse_result(result_raw)
    if result is None:
        return ReviewReason.RESULTADO_INVALIDO
    if result is CallResult.ACUERDO:
        if offer_id is None:
            return ReviewReason.ACUERDO_SIN_OFERTA
        if offered_ids is None:
            return ReviewReason.ACUERDO_SIN_FOTO
        if offer_id not in offered_ids:
            return ReviewReason.OFERTA_DESCONOCIDA
    return None
