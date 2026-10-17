"""Endpoints de negociación: reglas de cada empresa y ofertas de un caso.

Todos requieren sesión. Permisos (se verifican en los casos de uso):
- VIEW_PORTFOLIO -> ver reglas y ofertas (administrador, operador, supervisor)
- MANAGE_RULES   -> crear y cambiar reglas (solo administrador)
"""

from uuid import UUID

from fastapi import APIRouter, status

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.modules.negotiation.api.schemas import CaseOffersOut, RuleIn, RuleOut
from mavic.modules.negotiation.application import offers, rules

router = APIRouter()


@router.get("/negotiation-rules", tags=["negotiation"])
def list_rules(session: SessionDep, actor: ActorDep) -> list[RuleOut]:
    """Reglas de la empresa, activas e inactivas."""
    return [RuleOut.from_view(rule) for rule in rules.list_rules(session, actor=actor)]


@router.post("/negotiation-rules", tags=["negotiation"], status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, session: SessionDep, actor: ActorDep) -> RuleOut:
    """Crea una regla. Falla con 409 `RULE_OVERLAP` si se pisa con otra activa."""
    return RuleOut.from_view(rules.create_rule(session, actor=actor, data=body.to_data()))


@router.put("/negotiation-rules/{rule_id}", tags=["negotiation"])
def update_rule(rule_id: UUID, body: RuleIn, session: SessionDep, actor: ActorDep) -> RuleOut:
    """Reemplaza la regla completa. Para desactivarla, mandala con `is_active: false`."""
    view = rules.update_rule(session, actor=actor, rule_id=rule_id, data=body.to_data())
    return RuleOut.from_view(view)


@router.get("/cases/{case_id}/offers", tags=["negotiation"])
def case_offers(
    case_id: UUID, session: SessionDep, actor: ActorDep, clock: ClockDep
) -> CaseOffersOut:
    """Qué se le puede ofrecer hoy al deudor de este caso, según la regla que le corresponde."""
    view = offers.offers_for_case(session, actor=actor, clock=clock, case_id=case_id)
    return CaseOffersOut.from_view(view)
