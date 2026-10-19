"""Resumen de la cartera para el tablero.

Todas las cuentas se hacen acá (en la base y en Python con Decimal), nunca en el
navegador: el frontend solo muestra los números (ADR-028).

Qué se cuenta:

    casos por estado      ──► cuántos y cuánto suman, para los 6 estados (con 0 si no hay)
    deuda en gestión      ──► casos que el agente todavía puede negociar
                              (pendientes y contactados), por tramo de atraso
    facturas sin caso     ──► vencidas (las que agruparía "Generar casos") y por vencer
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.portfolio.domain.cases import (
    AGE_BUCKETS,
    NEGOTIABLE_STATUSES,
    CaseStatus,
    age_bucket,
    debt_age_days,
)
from mavic.modules.portfolio.infrastructure.repositories import CaseRepository, InvoiceRepository

CENT = Decimal("0.01")
# Solo se aceptan facturas en pesos (values.parse_currency): sumar es correcto.
# Si se agrega otra moneda, este resumen tiene que separar por moneda.
CURRENCY = "ARS"


def _money(amount: Decimal) -> Decimal:
    """Siempre con 2 decimales: 0 -> 0.00, para que el JSON sea parejo."""
    return amount.quantize(CENT)


@dataclass(frozen=True)
class Bucket:
    """Casos y monto de un grupo (un estado o un tramo de atraso)."""

    key: str
    cases: int
    amount: Decimal


@dataclass(frozen=True)
class PortfolioSummary:
    currency: str
    cases_total: int
    amount_total: Decimal
    by_status: list[Bucket]  # los 6 estados, en el orden de CaseStatus
    in_progress_cases: int  # pendientes + contactados
    in_progress_amount: Decimal
    in_progress_by_age: list[Bucket]  # los 4 tramos de AGE_BUCKETS
    unassigned_overdue_invoices: int
    unassigned_overdue_amount: Decimal
    upcoming_invoices: int
    upcoming_amount: Decimal


def portfolio_summary(session: Session, *, actor: Actor, clock: Clock) -> PortfolioSummary:
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()
    today = clock.today()
    cases = CaseRepository(session)

    # Los estados sin casos no vienen de la base: se completan con 0.
    found = {
        status: (count, amount) for status, count, amount in cases.totals_by_status(company_id)
    }
    by_status = []
    for status in CaseStatus:
        count, amount = found.get(status, (0, Decimal(0)))
        by_status.append(Bucket(status.value, count, _money(amount)))

    ages: dict[str, tuple[int, Decimal]] = {name: (0, Decimal(0)) for name, _, _ in AGE_BUCKETS}
    for oldest_due_date, amount in cases.debts_in_status(company_id, NEGOTIABLE_STATUSES):
        name = age_bucket(debt_age_days(oldest_due_date, today))
        count, total = ages[name]
        ages[name] = (count + 1, total + amount)
    by_age = [Bucket(name, count, _money(total)) for name, (count, total) in ages.items()]

    unassigned = InvoiceRepository(session).unassigned_totals(company_id, today)

    return PortfolioSummary(
        currency=CURRENCY,
        cases_total=sum(b.cases for b in by_status),
        amount_total=_money(sum((b.amount for b in by_status), Decimal(0))),
        by_status=by_status,
        in_progress_cases=sum(b.cases for b in by_age),
        in_progress_amount=_money(sum((b.amount for b in by_age), Decimal(0))),
        in_progress_by_age=by_age,
        unassigned_overdue_invoices=unassigned.overdue_count,
        unassigned_overdue_amount=_money(unassigned.overdue_amount),
        upcoming_invoices=unassigned.upcoming_count,
        upcoming_amount=_money(unassigned.upcoming_amount),
    )
