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
