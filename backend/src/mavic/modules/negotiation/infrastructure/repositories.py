"""Acceso a la tabla de reglas. Toda consulta va filtrada por empresa."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from mavic.modules.negotiation.infrastructure.orm import NegotiationRuleModel

# Cada tipo de bloqueo usa su propio "espacio" de números, para no chocar con el
# de la cartera (1001).
_RULES_LOCK_NAMESPACE = 1002


def lock_company_rules(session: Session, company_id: uuid.UUID) -> None:
    """Un solo cambio de reglas a la vez por empresa.

    Problema: Laura y otra administradora crean al mismo tiempo dos reglas que se
    pisan. Cada una revisa las reglas existentes, no ve la de la otra (todavía no
    se guardó) y las dos se guardan. Resultado: un caso con dos reglas posibles.

    Con este bloqueo, la segunda espera a que la primera termine y recién ahí
    revisa: ve la regla nueva y se rechaza. Se libera solo al terminar la transacción.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:company_id))"),
        {"namespace": _RULES_LOCK_NAMESPACE, "company_id": str(company_id)},
    )


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, rule: NegotiationRuleModel) -> None:
        self._session.add(rule)

    def get(self, company_id: uuid.UUID, rule_id: uuid.UUID) -> NegotiationRuleModel | None:
        return self._session.scalar(
            select(NegotiationRuleModel).where(
                NegotiationRuleModel.company_id == company_id,
                NegotiationRuleModel.id == rule_id,
            )
        )

    def of_company(
        self, company_id: uuid.UUID, *, only_active: bool = False
    ) -> list[NegotiationRuleModel]:
        query = select(NegotiationRuleModel).where(NegotiationRuleModel.company_id == company_id)
        if only_active:
            query = query.where(NegotiationRuleModel.is_active.is_(True))
        order = (NegotiationRuleModel.min_amount, NegotiationRuleModel.min_debt_age_days)
        return list(self._session.scalars(query.order_by(*order, NegotiationRuleModel.name)))

    def name_taken(
        self, company_id: uuid.UUID, name: str, *, except_id: uuid.UUID | None = None
    ) -> bool:
        query = select(NegotiationRuleModel.id).where(
            NegotiationRuleModel.company_id == company_id,
            func.lower(NegotiationRuleModel.name) == name.lower(),
        )
        if except_id is not None:
            query = query.where(NegotiationRuleModel.id != except_id)
        return self._session.scalar(query) is not None
