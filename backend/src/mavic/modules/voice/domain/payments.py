"""Seguimiento de pagos de un acuerdo: cuotas con fecha y estado.

Cuando el deudor acepta una oferta, Mavic arma las cuotas con sus fechas:

    acuerdo del 16/10  +  plazo de la regla (5 días)
        cuota 1: 21/10
        cuota 2: 21/11   (un mes después)
        cuota 3: 21/12

El pago único es un acuerdo de UNA cuota. Las fechas no las pacta el agente
(no tiene herramientas para eso): salen del plazo de la regla, el mismo que
usa la oferta ("a pagar en 5 días").

Cada cuota se marca como pagada a mano (lo hace una persona de la empresa).
El estado del acuerdo NO se guarda: se calcula cada vez, así nunca queda viejo.

    todas pagas ──────────────────────────────> CUMPLIDO
    alguna sin pagar con fecha ya pasada ─────> ATRASADO
    el resto ─────────────────────────────────> AL DÍA

Atrasado no es definitivo: si el deudor paga lo vencido, vuelve a estar al día.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from mavic.core.errors import BusinessRuleViolationError

# Si la regla no se encuentra (no debería pasar: las reglas no se borran).
DEFAULT_PAYMENT_DAYS = 5


class AgreementStatus(StrEnum):
    ACTIVE = "active"  # al día: no tiene cuotas vencidas sin pagar
    FULFILLED = "fulfilled"  # cumplido: pagó todo
    LATE = "late"  # atrasado: se le pasó una fecha sin pagar


@dataclass(frozen=True)
class PlannedInstallment:
    number: int  # empieza en 1
    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class InstallmentState:
    due_date: date
    amount: Decimal
    paid_on: date | None


def add_months(day: date, months: int) -> date:
    """El mismo día, `months` meses después. Si ese mes es más corto, el último día.

    >>> add_months(date(2026, 1, 31), 1)
    datetime.date(2026, 2, 28)
    >>> add_months(date(2026, 11, 21), 2)
    datetime.date(2027, 1, 21)
    """
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def plan_installments(
    *, agreed_on: date, payment_days: int, count: int, amount: Decimal
) -> list[PlannedInstallment]:
    """Las cuotas de un acuerdo: la primera vence a los `payment_days` días, el resto cada mes.

    `amount` es el importe de cada cuota (en un pago único, el total).
    """
    if count < 1:
        raise ValueError("Un acuerdo tiene al menos una cuota.")
    first = agreed_on + timedelta(days=payment_days)
    return [
        PlannedInstallment(number=n, due_date=add_months(first, n - 1), amount=amount)
        for n in range(1, count + 1)
    ]


def agreement_status(installments: list[InstallmentState], today: date) -> AgreementStatus:
    if all(i.paid_on is not None for i in installments):
        return AgreementStatus.FULFILLED
    if any(i.paid_on is None and i.due_date < today for i in installments):
        return AgreementStatus.LATE
    return AgreementStatus.ACTIVE


def validate_payment_date(paid_on: date, *, agreed_on: date, today: date) -> None:
    """Un pago no puede ser del futuro ni de antes del acuerdo."""
    if paid_on > today:
        raise BusinessRuleViolationError(
            "La fecha de pago no puede ser posterior a hoy.", code="PAYMENT_DATE_IN_FUTURE"
        )
    if paid_on < agreed_on:
        raise BusinessRuleViolationError(
            "La fecha de pago no puede ser anterior al acuerdo.", code="PAYMENT_BEFORE_AGREEMENT"
        )
