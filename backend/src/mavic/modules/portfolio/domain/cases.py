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
