"""El tablero: un solo pedido con todo lo que muestra la pantalla de inicio.

    GET /dashboard
        ├─ cartera  (portfolio.application.summary)
        ├─ agente   (voice.application.summary)
        └─ pagos    (voice.application.payments: lo cobrado de los acuerdos)

Cada parte controla sus propios permisos; este módulo solo las junta.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.portfolio.application.summary import PortfolioSummary, portfolio_summary
from mavic.modules.voice.application.payments import PaymentTotals, payment_totals
from mavic.modules.voice.application.summary import AgentSummary, agent_summary


@dataclass(frozen=True)
class Dashboard:
    as_of: date  # los días de atraso se cuentan a esta fecha
    portfolio: PortfolioSummary
    agent: AgentSummary
    payments: PaymentTotals


def dashboard(session: Session, *, actor: Actor, clock: Clock) -> Dashboard:
    agent = agent_summary(session, actor=actor)  # controla el permiso de ver la cartera
    return Dashboard(
        as_of=clock.today(),
        portfolio=portfolio_summary(session, actor=actor, clock=clock),
        agent=agent,
        payments=payment_totals(session, company_id=actor.require_company(), today=clock.today()),
    )
