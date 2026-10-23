"""Medidor de costos: cuánto costó el uso del mes y cuánto va a costar a fin de mes.

    uso real (de las tablas de Mavic)          ×  tarifa (la carga administración)
    minutos de llamada (duración del webhook)     por minuto
    emails mandados                               por email
    WhatsApp mandados                             por mensaje

La plata NO sale de las facturas de los proveedores (Mavic no las lee): es el
uso real multiplicado por las tarifas que carga la empresa. Si las tarifas
están bien cargadas, el número es una estimación muy cercana.

Proyección a fin de mes (solo el mes en curso): lo gastado hasta hoy, al mismo
ritmo, hasta el último día.

    gastado 10/10: $ 300  ──>  $ 300 / 10 días × 31 días = $ 930
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
ZERO = Decimal("0")


class Concept(StrEnum):
    CALLS = "calls"  # minutos de llamada
    EMAIL = "email"
    WHATSAPP = "whatsapp"


@dataclass(frozen=True)
class Rates:
    currency: str  # moneda de las tarifas (USD por defecto: así cobran los proveedores)
    call_minute: Decimal
    email: Decimal
    whatsapp: Decimal
    monthly_budget: Decimal | None  # tope mensual opcional

    def of(self, concept: Concept) -> Decimal:
        return {
            Concept.CALLS: self.call_minute,
            Concept.EMAIL: self.email,
            Concept.WHATSAPP: self.whatsapp,
        }[concept]


NO_RATES = Rates("USD", ZERO, ZERO, ZERO, None)
MAX_RATE = Decimal("1000")  # por unidad: más que esto es casi seguro un error de tipeo


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def minutes(seconds: int) -> Decimal:
    """Minutos exactos (sin redondear al minuto: 90 s = 1,5 min).

    >>> minutes(90)
    Decimal('1.5')
    """
    return Decimal(seconds) / Decimal(60)


@dataclass(frozen=True)
class MonthSpan:
    month: date  # el día 1
    days_in_month: int
    days_counted: int  # días que ya pasaron (para proyectar); 0 si es futuro


def month_span(month: date, today: date) -> MonthSpan:
    """
    >>> month_span(date(2026, 10, 1), date(2026, 10, 10))
    MonthSpan(month=datetime.date(2026, 10, 1), days_in_month=31, days_counted=10)
    >>> month_span(date(2026, 9, 1), date(2026, 10, 10)).days_counted
    30
    """
    first = month.replace(day=1)
    days = calendar.monthrange(first.year, first.month)[1]
    if (first.year, first.month) == (today.year, today.month):
        counted = today.day
    elif first < today:
        counted = days
    else:
        counted = 0
    return MonthSpan(first, days, counted)


def project(cost: Decimal, span: MonthSpan) -> Decimal:
    """Lo que va a costar el mes completo si sigue al mismo ritmo.

    >>> project(Decimal("300"), MonthSpan(date(2026, 10, 1), 31, 10))
    Decimal('930.00')
    """
    if span.days_counted == 0:
        return money(cost)
    return money(cost * span.days_in_month / span.days_counted)


class BudgetStatus(StrEnum):
    NO_BUDGET = "no_budget"
    OK = "ok"  # la proyección queda debajo del 80 % del tope
    HIGH = "high"  # la proyección pasa el 80 % del tope
    OVER_PROJECTION = "over_projection"  # la proyección pasa el tope
    OVER_BUDGET = "over_budget"  # lo gastado ya pasó el tope


def budget_status(total: Decimal, projected: Decimal, budget: Decimal | None) -> BudgetStatus:
    """
    >>> budget_status(Decimal("50"), Decimal("120"), Decimal("100"))
    <BudgetStatus.OVER_PROJECTION: 'over_projection'>
    """
    if budget is None or budget <= 0:
        return BudgetStatus.NO_BUDGET
    if total > budget:
        return BudgetStatus.OVER_BUDGET
    if projected > budget:
        return BudgetStatus.OVER_PROJECTION
    if projected > budget * Decimal("0.8"):
        return BudgetStatus.HIGH
    return BudgetStatus.OK
