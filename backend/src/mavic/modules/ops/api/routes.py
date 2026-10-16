"""Health checks.

Dos preguntas distintas, dos endpoints:

- `/health`        ¿El proceso está vivo?          No toca la base. Siempre rápido.
- `/health/ready`  ¿Puede atender requests reales?  Verifica la base de datos.

Si la base no responde, `/health/ready` devuelve 503 con el formato de error
común, en lugar de un 500 con una traza.

Los endpoints son `def` (no `async def`) a propósito: el ping a la base es una
operación bloqueante, y FastAPI ejecuta los `def` en un pool de hilos para que
no frenen al resto de los requests.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from mavic.api.deps import DatabaseDep
from mavic.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def readiness(database: DatabaseDep) -> HealthResponse:
    try:
        database.ping()
    except SQLAlchemyError as exc:
        # Se loguea el detalle técnico; al cliente le llega un mensaje genérico.
        logger.warning("La base de datos no responde: %s", type(exc).__name__)
        raise ExternalServiceError(
            "La base de datos no está disponible.", service="database"
        ) from exc
    return HealthResponse(status="ready")
