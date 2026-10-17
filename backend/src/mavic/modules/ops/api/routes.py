"""Health checks.

Dos preguntas distintas, dos endpoints:

- `/health`        ¿El proceso está vivo?          No toca la base. Siempre rápido.
- `/health/ready`  ¿Puede atender requests reales?  Verifica la base de datos.

Si la base no responde, `Database.ping()` lanza un ExternalServiceError y el
manejador global devuelve 503 con el formato de error común, sin trazas.

Los endpoints son `def` (no `async def`) a propósito: el ping a la base es una
operación bloqueante, y FastAPI ejecuta los `def` en un pool de hilos para que
no frenen al resto de los requests.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from mavic.api.deps import DatabaseDep

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def readiness(database: DatabaseDep) -> HealthResponse:
    database.ping()
    return HealthResponse(status="ready")
