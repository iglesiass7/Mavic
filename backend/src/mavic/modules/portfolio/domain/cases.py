"""Casos de cobranza: estados, etapa de una factura y antigüedad de la deuda.

Un CASO agrupa las facturas vencidas de un deudor. Es la unidad con la que
trabaja el agente de voz: llama por el caso completo, no por cada factura.

Estados (los resultados vienen de los que registra el agente de voz):

    pending ──llamada──> contacted   (CONTACTADO: habló, sin acuerdo)
                    ├──> agreement   (ACUERDO de pago)
                    ├──> disputed    (DESCONOCIMIENTO: dice que no debe)
                    └──> escalated   (DERIVACION_HUMANA: lo atiende una persona)
    cualquiera ────────> closed      (cerrado a mano)

En este paso todos los casos nacen en `pending`. Las transiciones llegan con
la integración del agente de voz.
"""

from datetime import date
from enum import StrEnum


class CaseStatus(StrEnum):
    PENDING = "pending"
    CONTACTED = "contacted"
    AGREEMENT = "agreement"
    DISPUTED = "disputed"
    ESCALATED = "escalated"
    CLOSED = "closed"


class InvoiceStage(StrEnum):
    """En qué momento está una factura respecto de su vencimiento."""

    UPCOMING = "upcoming"  # todavía no vence
    DUE_TODAY = "due_today"  # vence hoy
    OVERDUE = "overdue"  # vencida: puede ir a un caso


def invoice_stage(due_date: date, today: date) -> InvoiceStage:
    """En el original esta cuenta la hacía el navegador; ahora la hace el backend."""
    if due_date > today:
        return InvoiceStage.UPCOMING
    if due_date == today:
        return InvoiceStage.DUE_TODAY
    return InvoiceStage.OVERDUE


def is_overdue(due_date: date, today: date) -> bool:
    return due_date < today


def debt_age_days(oldest_due_date: date, today: date) -> int:
    """Días de mora: desde el vencimiento más viejo del caso. Nunca negativo."""
    return max((today - oldest_due_date).days, 0)


# Tramos de antigüedad para el tablero: (nombre, desde, hasta). None = sin tope.
# Son los cortes habituales en cobranzas (30/60/90 días).
AGE_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0_30", 0, 30),
    ("31_60", 31, 60),
    ("61_90", 61, 90),
    ("91_plus", 91, None),
)


def age_bucket(days: int) -> str:
    """En qué tramo cae una deuda según sus días de atraso.

    >>> age_bucket(0), age_bucket(30), age_bucket(31), age_bucket(90), age_bucket(400)
    ('0_30', '0_30', '31_60', '61_90', '91_plus')
    """
    for name, low, high in AGE_BUCKETS:
        if days >= low and (high is None or days <= high):
            return name
    return AGE_BUCKETS[0][0]  # días negativos no existen (debt_age_days nunca da < 0)


# Se negocia con casos que todavía no tienen un resultado. Con un acuerdo, una
# disputa o una derivación, ofrecer otra cosa generaría confusión.
NEGOTIABLE_STATUSES = frozenset({CaseStatus.PENDING, CaseStatus.CONTACTED})

# Resultados que puede dejar una llamada sobre un caso negociable.
CALL_OUTCOME_STATUSES = frozenset(
    {CaseStatus.CONTACTED, CaseStatus.AGREEMENT, CaseStatus.DISPUTED, CaseStatus.ESCALATED}
)


def is_negotiable(status: CaseStatus) -> bool:
    return status in NEGOTIABLE_STATUSES
