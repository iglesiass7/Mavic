"""Casos de uso de las reglas de negociación (CU-06).

- Ver las reglas:       cualquier usuario de la empresa (VIEW_PORTFOLIO).
- Crear o cambiar una:  solo quien tiene MANAGE_RULES (el administrador).

No hay "borrar": una regla se DESACTIVA. Así se conserva qué regla generó cada
oferta, y se puede volver a activar.
"""

import uuid
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.core.errors import BusinessRuleViolationError, ConflictError, NotFoundError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditAction, Subject, changes
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.negotiation.domain.offers import CENT
from mavic.modules.negotiation.domain.rules import (
    CaseFacts,
    Interval,
    PaymentTerms,
    RuleConditions,
    applies_to,
    conditions_overlap,
    validate_conditions,
    validate_terms,
)
from mavic.modules.negotiation.infrastructure.orm import NegotiationRuleModel
from mavic.modules.negotiation.infrastructure.repositories import (
    RuleRepository,
    lock_company_rules,
)


@dataclass(frozen=True)
class RuleData:
    """Lo que escribe el administrador al crear o cambiar una regla."""

    name: str
    description: str
    conditions: RuleConditions
    terms: PaymentTerms
    is_active: bool = True


@dataclass(frozen=True)
class RuleView:
    id: uuid.UUID
    name: str
    description: str
    conditions: RuleConditions
    terms: PaymentTerms
    is_active: bool

    @classmethod
    def from_model(cls, rule: NegotiationRuleModel) -> "RuleView":
        return cls(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            conditions=conditions_of(rule),
            terms=terms_of(rule),
            is_active=rule.is_active,
        )


# ---------------------------------------------------------------- traducción tabla <-> dominio


def conditions_of(rule: NegotiationRuleModel) -> RuleConditions:
    return RuleConditions(
        amount=Interval(rule.min_amount, rule.max_amount),
        debt_age_days=Interval(rule.min_debt_age_days, rule.max_debt_age_days),
        invoice_count=Interval(rule.min_invoice_count, rule.max_invoice_count),
    )


def terms_of(rule: NegotiationRuleModel) -> PaymentTerms:
    return PaymentTerms(
        discount_pct=rule.discount_pct,
        payment_days=rule.payment_days,
        max_installments=rule.max_installments,
        interest_pct=rule.interest_pct,
    )


def _write(rule: NegotiationRuleModel, data: RuleData) -> None:
    rule.name = data.name
    rule.description = data.description
    rule.min_amount = data.conditions.amount.minimum
    rule.max_amount = data.conditions.amount.maximum
    rule.min_debt_age_days = data.conditions.debt_age_days.minimum
    rule.max_debt_age_days = data.conditions.debt_age_days.maximum
    rule.min_invoice_count = data.conditions.invoice_count.minimum
    rule.max_invoice_count = data.conditions.invoice_count.maximum
    rule.discount_pct = data.terms.discount_pct
    rule.payment_days = data.terms.payment_days
    rule.max_installments = data.terms.max_installments
    rule.interest_pct = data.terms.interest_pct
    rule.is_active = data.is_active


def _snapshot(rule: NegotiationRuleModel) -> dict[str, object]:
    """La regla con nombres legibles, para la auditoría (antes / después)."""
    return {
        "Nombre": rule.name,
        "Descripción": rule.description,
        "Monto desde": str(rule.min_amount),
        "Monto hasta": None if rule.max_amount is None else str(rule.max_amount),
        "Atraso desde (días)": rule.min_debt_age_days,
        "Atraso hasta (días)": rule.max_debt_age_days,
        "Facturas desde": rule.min_invoice_count,
        "Facturas hasta": rule.max_invoice_count,
        "Descuento (%)": str(rule.discount_pct),
        "Plazo para pagar (días)": rule.payment_days,
        "Cuotas máximas": rule.max_installments,
        "Interés (%)": str(rule.interest_pct),
        "Activa": rule.is_active,
    }


def _subject(rule: NegotiationRuleModel) -> Subject:
    return Subject("rule", str(rule.id), f"Regla '{rule.name}'")


# ---------------------------------------------------------------- reglas compartidas


def _cents(value: Decimal) -> Decimal:
    """Montos y porcentajes con 2 decimales, igual que en la base ("12.5" -> "12.50")."""
    return value.quantize(CENT)


def _clean(data: RuleData) -> RuleData:
    amount = data.conditions.amount
    data = replace(
        data,
        name=data.name.strip(),
        description=data.description.strip(),
        conditions=replace(
            data.conditions,
            amount=Interval(
                _cents(amount.minimum), None if amount.maximum is None else _cents(amount.maximum)
            ),
        ),
        terms=replace(
            data.terms,
            discount_pct=_cents(data.terms.discount_pct),
            interest_pct=_cents(data.terms.interest_pct),
        ),
    )
    if not data.name:
        raise BusinessRuleViolationError("La regla necesita un nombre.", code="RULE_NAME_REQUIRED")
    validate_conditions(data.conditions)
    validate_terms(data.terms)
    return data


def _check_against_others(
    repository: RuleRepository,
    company_id: uuid.UUID,
    data: RuleData,
    except_id: uuid.UUID | None = None,
) -> None:
    if repository.name_taken(company_id, data.name, except_id=except_id):
        raise ConflictError(f"Ya existe una regla llamada '{data.name}'.", code="RULE_NAME_TAKEN")
    if not data.is_active:
        return  # una regla inactiva no compite con nadie
    for other in repository.of_company(company_id, only_active=True):
        if other.id != except_id and conditions_overlap(data.conditions, conditions_of(other)):
            raise ConflictError(
                f"Se pisa con la regla activa '{other.name}': habría casos con dos ofertas "
                "posibles. Ajustá los rangos o desactivá una de las dos.",
                code="RULE_OVERLAP",
                details={"rule_id": str(other.id), "rule_name": other.name},
            )


def find_rule_for(
    rules: list[NegotiationRuleModel], facts: CaseFacts
) -> NegotiationRuleModel | None:
    """La regla activa que corresponde a un caso, o None si ninguna aplica.

    Como las reglas activas no se pisan, hay como máximo una.
    """
    return next((r for r in rules if r.is_active and applies_to(conditions_of(r), facts)), None)


# ---------------------------------------------------------------- casos de uso


def list_rules(session: Session, *, actor: Actor) -> list[RuleView]:
    actor.require(Permission.VIEW_PORTFOLIO)
    rules = RuleRepository(session).of_company(actor.require_company())
    return [RuleView.from_model(rule) for rule in rules]


def create_rule(session: Session, *, actor: Actor, data: RuleData) -> RuleView:
    actor.require(Permission.MANAGE_RULES)
    company_id = actor.require_company()
    data = _clean(data)

    lock_company_rules(session, company_id)
    repository = RuleRepository(session)
    _check_against_others(repository, company_id, data)

    rule = NegotiationRuleModel(company_id=company_id)
    _write(rule, data)
    repository.add(rule)
    session.flush()  # para que la regla tenga id
    audit.record(
        session,
        company_id=company_id,
        actor=actor,
        action=AuditAction.RULE_CREATED,
        subject=_subject(rule),
        summary=f"Creó la regla '{rule.name}'" + ("" if rule.is_active else " (inactiva)") + ".",
        details={"regla": _snapshot(rule)},
    )
    session.commit()
    return RuleView.from_model(rule)


def update_rule(session: Session, *, actor: Actor, rule_id: uuid.UUID, data: RuleData) -> RuleView:
    """Reemplaza la regla completa (también sirve para activarla o desactivarla)."""
    actor.require(Permission.MANAGE_RULES)
    company_id = actor.require_company()
    data = _clean(data)

    lock_company_rules(session, company_id)
    repository = RuleRepository(session)
    rule = repository.get(company_id, rule_id)
    if rule is None:
        raise NotFoundError("La regla no existe.", code="RULE_NOT_FOUND")
    _check_against_others(repository, company_id, data, except_id=rule.id)

    before = _snapshot(rule)
    _write(rule, data)
    diff = changes(before, _snapshot(rule))
    if diff:  # guardar sin cambios no deja un evento vacío
        if set(diff) == {"Activa"}:
            summary = f"{'Activó' if rule.is_active else 'Desactivó'} la regla '{rule.name}'."
        else:
            fields = ", ".join(key.lower() for key in diff)
            summary = f"Cambió la regla '{rule.name}': {fields}."
        audit.record(
            session,
            company_id=company_id,
            actor=actor,
            action=AuditAction.RULE_UPDATED,
            subject=_subject(rule),
            summary=summary,
            details={"cambios": diff},
        )
    session.commit()
    return RuleView.from_model(rule)
