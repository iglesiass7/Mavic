"""El tablero. Requiere sesión y el permiso VIEW_PORTFOLIO (lo controlan los casos de uso)."""

from fastapi import APIRouter

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.modules.reporting.api.schemas import DashboardOut
from mavic.modules.reporting.application import dashboard as reports

router = APIRouter()


@router.get("/dashboard", response_model=DashboardOut, tags=["dashboard"])
def get_dashboard(session: SessionDep, actor: ActorDep, clock: ClockDep) -> DashboardOut:
    """Números de la cartera y del agente, calculados con los datos de la empresa."""
    return DashboardOut.from_view(reports.dashboard(session, actor=actor, clock=clock))
