"""Resumen de lo que hizo el agente de voz, para el tablero.

    llamadas            ──► cuántas, en cuántas se verificó la identidad, la última
    resultados          ──► los 4 resultados posibles (con 0 si no hubo)
    acuerdos            ──► cuántos, de pago único o en cuotas, y los montos

Los montos de los acuerdos son lo que el deudor se COMPROMETIÓ a pagar en la
llamada, no plata cobrada: Mavic todavía no registra pagos.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.voice.domain.outcomes import CallResult
from mavic.modules.voice.infrastructure.repositories import agreement_totals, call_totals

CENT = Decimal("0.01")


@dataclass(frozen=True)
class AgentSummary:
    calls: int
    identity_verified: int
    calls_by_result: dict[str, int]  # los 4 de CallResult, en ese orden
    calls_without_result: int  # la llamada terminó antes de registrar un resultado
    last_call_at: datetime | None
    agreements: int
    agreements_single_payment: int
    agreements_installments: int
    agreed_original_amount: Decimal
    agreed_amount: Decimal


def agent_summary(session: Session, *, actor: Actor) -> AgentSummary:
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()

    calls = call_totals(session, company_id)
    by_result = {result.value: calls.by_result.get(result.value, 0) for result in CallResult}
    agreements = agreement_totals(session, company_id)

    return AgentSummary(
        calls=calls.calls,
        identity_verified=calls.identity_verified,
        calls_by_result=by_result,
        calls_without_result=calls.calls - sum(by_result.values()),
        last_call_at=calls.last_call_at,
        agreements=agreements.agreements,
        agreements_single_payment=agreements.single_payment,
        agreements_installments=agreements.installments,
        agreed_original_amount=agreements.original_amount.quantize(CENT),
        agreed_amount=agreements.agreed_amount.quantize(CENT),
    )
