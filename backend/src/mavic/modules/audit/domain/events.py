"""Qué se registra en la auditoría y con qué nivel.

La auditoría responde "quién hizo qué, cuándo y sobre qué". Cada cambio que
importa deja un evento, escrito EN LA MISMA TRANSACCIÓN que el cambio: si el
cambio se guarda, el evento también; si falla, no queda ninguno de los dos.

    regla cambiada ──┐
                     ├── commit ──> los dos quedan, o ninguno
    evento ──────────┘

Los eventos no se editan ni se borran (la base lo impide, ver la migración).

Niveles, como en la pantalla de Rynx:
- CRITICAL: cambia lo que hace el sistema o quién accede (reglas, usuarios,
  tarifas, avisos, anular un pago).
- INFO: trabajo del día (cargas, llamadas, pagos registrados).
- SYSTEM: lo hizo Mavic o el agente solo (resultado de una llamada, avisos enviados).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AuditLevel(StrEnum):
    CRITICAL = "critical"
    INFO = "info"
    SYSTEM = "system"


class ActorKind(StrEnum):
    USER = "user"  # una persona con sesión
    AGENT = "agent"  # el agente de voz (llega por el webhook o sus herramientas)
    SYSTEM = "system"  # un proceso de Mavic (por ejemplo, el envío de avisos)


class AuditAction(StrEnum):
    # Configuración: reglas, usuarios, empresas, avisos y tarifas
    RULE_CREATED = "RULE_CREATED"
    RULE_UPDATED = "RULE_UPDATED"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"  # noqa: S105 - nombre del evento, no una clave
    COMPANY_CREATED = "COMPANY_CREATED"
    REMINDER_SETTINGS_UPDATED = "REMINDER_SETTINGS_UPDATED"
    COST_RATES_UPDATED = "COST_RATES_UPDATED"
    # Cartera
    INVOICES_IMPORTED = "INVOICES_IMPORTED"
    CASES_GENERATED = "CASES_GENERATED"
    CASE_ESCALATED = "CASE_ESCALATED"
    # Llamadas y acuerdos
    CALL_STARTED = "CALL_STARTED"
    CALL_FAILED = "CALL_FAILED"
    CALL_FINISHED = "CALL_FINISHED"
    CALL_NEEDS_REVIEW = "CALL_NEEDS_REVIEW"
    AGREEMENT_CREATED = "AGREEMENT_CREATED"
    # Pagos
    PAYMENT_RECORDED = "PAYMENT_RECORDED"
    PAYMENT_UNDONE = "PAYMENT_UNDONE"
    AGREEMENT_FULFILLED = "AGREEMENT_FULFILLED"
    # Avisos
    REMINDERS_SENT = "REMINDERS_SENT"
    REMINDERS_NOT_SENT = "REMINDERS_NOT_SENT"  # el envío automático no pudo correr


LEVEL: dict[AuditAction, AuditLevel] = {
    AuditAction.RULE_CREATED: AuditLevel.CRITICAL,
    AuditAction.RULE_UPDATED: AuditLevel.CRITICAL,
    AuditAction.USER_CREATED: AuditLevel.CRITICAL,
    AuditAction.USER_UPDATED: AuditLevel.CRITICAL,
    AuditAction.PASSWORD_CHANGED: AuditLevel.INFO,
    AuditAction.COMPANY_CREATED: AuditLevel.CRITICAL,
    AuditAction.REMINDER_SETTINGS_UPDATED: AuditLevel.CRITICAL,
    AuditAction.COST_RATES_UPDATED: AuditLevel.CRITICAL,
    AuditAction.INVOICES_IMPORTED: AuditLevel.INFO,
    AuditAction.CASES_GENERATED: AuditLevel.INFO,
    AuditAction.CASE_ESCALATED: AuditLevel.INFO,
    AuditAction.CALL_STARTED: AuditLevel.INFO,
    AuditAction.CALL_FAILED: AuditLevel.INFO,
    AuditAction.CALL_FINISHED: AuditLevel.SYSTEM,
    AuditAction.CALL_NEEDS_REVIEW: AuditLevel.SYSTEM,
    AuditAction.AGREEMENT_CREATED: AuditLevel.SYSTEM,
    AuditAction.PAYMENT_RECORDED: AuditLevel.INFO,
    AuditAction.PAYMENT_UNDONE: AuditLevel.CRITICAL,
    AuditAction.AGREEMENT_FULFILLED: AuditLevel.SYSTEM,
    AuditAction.REMINDERS_SENT: AuditLevel.INFO,  # a mano o solo: lo dice quién lo hizo
    AuditAction.REMINDERS_NOT_SENT: AuditLevel.SYSTEM,
}


@dataclass(frozen=True)
class Subject:
    """Sobre qué fue el evento: "Caso #12", "Regla 'Mora alta'", "Pablo Díaz"."""

    kind: str  # case, rule, user, company, import, call, agreement, settings
    id: str | None
    label: str


def changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Los campos que cambiaron, con el valor de antes y el de después.

    >>> changes({"descuento": "10", "cuotas": 3}, {"descuento": "15", "cuotas": 3})
    {'descuento': {'antes': '10', 'despues': '15'}}
    """
    return {
        key: {"antes": before.get(key), "despues": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


class AuditCategory(StrEnum):
    """Para filtrar la pantalla por tema."""

    SETTINGS = "settings"  # reglas, usuarios, empresas, avisos, tarifas
    PORTFOLIO = "portfolio"  # cargas, casos
    CALLS = "calls"  # llamadas y acuerdos
    PAYMENTS = "payments"
    REMINDERS = "reminders"


CATEGORY: dict[AuditAction, AuditCategory] = {
    AuditAction.RULE_CREATED: AuditCategory.SETTINGS,
    AuditAction.RULE_UPDATED: AuditCategory.SETTINGS,
    AuditAction.USER_CREATED: AuditCategory.SETTINGS,
    AuditAction.USER_UPDATED: AuditCategory.SETTINGS,
    AuditAction.PASSWORD_CHANGED: AuditCategory.SETTINGS,
    AuditAction.COMPANY_CREATED: AuditCategory.SETTINGS,
    AuditAction.REMINDER_SETTINGS_UPDATED: AuditCategory.SETTINGS,
    AuditAction.COST_RATES_UPDATED: AuditCategory.SETTINGS,
    AuditAction.INVOICES_IMPORTED: AuditCategory.PORTFOLIO,
    AuditAction.CASES_GENERATED: AuditCategory.PORTFOLIO,
    AuditAction.CASE_ESCALATED: AuditCategory.PORTFOLIO,
    AuditAction.CALL_STARTED: AuditCategory.CALLS,
    AuditAction.CALL_FAILED: AuditCategory.CALLS,
    AuditAction.CALL_FINISHED: AuditCategory.CALLS,
    AuditAction.CALL_NEEDS_REVIEW: AuditCategory.CALLS,
    AuditAction.AGREEMENT_CREATED: AuditCategory.CALLS,
    AuditAction.PAYMENT_RECORDED: AuditCategory.PAYMENTS,
    AuditAction.PAYMENT_UNDONE: AuditCategory.PAYMENTS,
    AuditAction.AGREEMENT_FULFILLED: AuditCategory.PAYMENTS,
    AuditAction.REMINDERS_SENT: AuditCategory.REMINDERS,
    AuditAction.REMINDERS_NOT_SENT: AuditCategory.REMINDERS,
}


def actions_in(category: AuditCategory) -> list[AuditAction]:
    return [action for action, group in CATEGORY.items() if group == category]
