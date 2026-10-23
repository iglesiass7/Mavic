"""Caso de uso: qué se le puede ofrecer a un deudor (CU-07).

    caso (de la cartera) --> monto, días de atraso, cantidad de facturas
                                   |
                                   v
    reglas activas de la empresa --> la regla que corresponde (una o ninguna)
                                   |
                                   v
    ofertas calculadas --> pago único con descuento + plan en cuotas

Si no hay oferta, se dice por qué (`reason`): el operador lo ve en pantalla y,
en el Paso 5, el agente de voz deriva el caso a una persona.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.negotiation.application.rules import find_rule_for, terms_of
from mavic.modules.negotiation.domain.offers import CallOffer, Offers, build_offers, call_offer_list
from mavic.modules.negotiation.domain.rules import CaseFacts
from mavic.modules.negotiation.infrastructure.repositories import RuleRepository
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.portfolio.domain.cases import CaseStatus, is_negotiable


class NoOfferReason(StrEnum):
    CASE_NOT_NEGOTIABLE = "CASE_NOT_NEGOTIABLE"  # el caso ya tiene un resultado
    NO_MATCHING_RULE = "NO_MATCHING_RULE"  # ninguna regla activa se aplica a este caso


@dataclass(frozen=True)
class RuleRef:
    id: uuid.UUID
    name: str
    # Días para el primer pago (y el vencimiento de la primera cuota). Con esto se
    # arman las fechas de las cuotas cuando el deudor acepta (seguimiento de pagos).
    payment_days: int


@dataclass(frozen=True)
class CaseOffersView:
    case_id: uuid.UUID
    case_number: int
    case_status: CaseStatus
    currency: str
    facts: CaseFacts
    rule: RuleRef | None
    offers: Offers | None
    reason: NoOfferReason | None
    # Lo que recibe el agente nuevo al llamar (ADR-034): lista ordenada, cuotas iguales.
    call_offers: list[CallOffer] = field(default_factory=list)


def offers_for_case(
    session: Session, *, actor: Actor, clock: Clock, case_id: uuid.UUID
) -> CaseOffersView:
    actor.require(Permission.VIEW_PORTFOLIO)
    return compute_case_offers(
        session, company_id=actor.require_company(), clock=clock, case_id=case_id
    )


def compute_case_offers(
    session: Session, *, company_id: uuid.UUID, clock: Clock, case_id: uuid.UUID
) -> CaseOffersView:
    """Las ofertas de un caso de esa empresa, sin chequeo de usuario (lo usa el agente).

    El caso se pide a la cartera por su caso de uso público, nunca leyendo sus tablas.
    """
    detail = portfolio.case_detail(session, company_id=company_id, clock=clock, case_id=case_id)
    summary = detail.summary
    facts = CaseFacts(
        total_amount=summary.total_amount,
        debt_age_days=summary.debt_age_days,
        invoice_count=summary.invoice_count,
    )

    def view(
        rule: RuleRef | None = None,
        offers: Offers | None = None,
        reason: NoOfferReason | None = None,
    ) -> CaseOffersView:
        return CaseOffersView(
            case_id=summary.id,
            case_number=summary.number,
            case_status=summary.status,
            currency=summary.currency,
            facts=facts,
            rule=rule,
            offers=offers,
            reason=reason,
        )

    if not is_negotiable(summary.status):
        return view(reason=NoOfferReason.CASE_NOT_NEGOTIABLE)

    rules = RuleRepository(session).of_company(company_id, only_active=True)
    rule = find_rule_for(rules, facts)
    if rule is None:
        return view(reason=NoOfferReason.NO_MATCHING_RULE)

    terms = terms_of(rule)
    return CaseOffersView(
        **{
            **view(
                rule=RuleRef(id=rule.id, name=rule.name, payment_days=rule.payment_days),
                offers=build_offers(terms, facts.total_amount, clock.today()),
            ).__dict__,
            "call_offers": call_offer_list(terms, facts.total_amount),
        }
    )


@dataclass(frozen=True)
class CaseCallOffers:
    """Lo que se le manda al agente al iniciar una llamada (ADR-034)."""

    rule: RuleRef | None
    offers: list[CallOffer]  # en orden de presentación; vacía si no hay regla
    reason: NoOfferReason | None


def call_offers_for_case(
    session: Session, *, company_id: uuid.UUID, clock: Clock, case_id: uuid.UUID
) -> CaseCallOffers:
    """Las ofertas ordenadas para llamar. Elige la regla igual que `compute_case_offers`."""
    summary = portfolio.case_detail(
        session, company_id=company_id, clock=clock, case_id=case_id
    ).summary
    if not is_negotiable(summary.status):
        return CaseCallOffers(rule=None, offers=[], reason=NoOfferReason.CASE_NOT_NEGOTIABLE)
    facts = CaseFacts(
        total_amount=summary.total_amount,
        debt_age_days=summary.debt_age_days,
        invoice_count=summary.invoice_count,
    )
    rule = find_rule_for(RuleRepository(session).of_company(company_id, only_active=True), facts)
    if rule is None:
        return CaseCallOffers(rule=None, offers=[], reason=NoOfferReason.NO_MATCHING_RULE)
    return CaseCallOffers(
        rule=RuleRef(id=rule.id, name=rule.name, payment_days=rule.payment_days),
        offers=call_offer_list(terms_of(rule), facts.total_amount),
        reason=None,
    )
