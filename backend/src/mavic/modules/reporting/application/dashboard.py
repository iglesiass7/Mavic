"""El tablero: un solo pedido con todo lo que muestra la pantalla de inicio.

    GET /dashboard
        ├─ cartera  (portfolio.application.summary)
        └─ agente   (voice.application.summary)

Cada parte controla sus propios permisos; este módulo solo las junta.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.portfolio.application.summary import PortfolioSummary, portfolio_summary
from mavic.modules.voice.application.summary import AgentSummary, agent_summary


@dataclass(frozen=True)
class Dashboard:
    as_of: date  # los días de atraso se cuentan a esta fecha
    portfolio: PortfolioSummary
    agent: AgentSummary


def dashboard(session: Session, *, actor: Actor, clock: Clock) -> Dashboard:
    return Dashboard(
        as_of=clock.today(),
        portfolio=portfolio_summary(session, actor=actor, clock=clock),
        agent=agent_summary(session, actor=actor),
    )
