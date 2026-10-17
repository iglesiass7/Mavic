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
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.negotiation.application.rules import find_rule_for, terms_of
from mavic.modules.negotiation.domain.offers import Offers, build_offers
from mavic.modules.negotiation.domain.rules import CaseFacts
from mavic.modules.negotiation.infrastructure.repositories import RuleRepository
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.portfolio.domain.cases import CaseStatus

# Se negocia con casos que todavía no tienen un resultado. Con un acuerdo, una
# disputa o una derivación, ofrecer otra cosa generaría confusión.
NEGOTIABLE_STATUSES = frozenset({CaseStatus.PENDING, CaseStatus.CONTACTED})


class NoOfferReason(StrEnum):
    CASE_NOT_NEGOTIABLE = "CASE_NOT_NEGOTIABLE"  # el caso ya tiene un resultado
    NO_MATCHING_RULE = "NO_MATCHING_RULE"  # ninguna regla activa se aplica a este caso


@dataclass(frozen=True)
class RuleRef:
    id: uuid.UUID
    name: str


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


def offers_for_case(
    session: Session, *, actor: Actor, clock: Clock, case_id: uuid.UUID
) -> CaseOffersView:
    # El caso se pide a la cartera por su caso de uso público: ahí ya se
    # verifican el permiso, la empresa del actor y que el caso exista.
    detail = portfolio.get_case(session, actor=actor, clock=clock, case_id=case_id)
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
            currency=detail.invoices[0].currency,
            facts=facts,
            rule=rule,
            offers=offers,
            reason=reason,
        )

    if summary.status not in NEGOTIABLE_STATUSES:
        return view(reason=NoOfferReason.CASE_NOT_NEGOTIABLE)

    rules = RuleRepository(session).of_company(actor.require_company(), only_active=True)
    rule = find_rule_for(rules, facts)
    if rule is None:
        return view(reason=NoOfferReason.NO_MATCHING_RULE)

    return view(
        rule=RuleRef(id=rule.id, name=rule.name),
        offers=build_offers(terms_of(rule), facts.total_amount, clock.today()),
    )
