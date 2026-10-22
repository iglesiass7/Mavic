"""Punto de entrada: arma la aplicación FastAPI.

Se usa el patrón "app factory": en vez de crear la app al importar el módulo,
una función `create_app()` la construye cuando se la pide. Ventajas:
- Importar el módulo no exige variables de entorno ni conecta a nada.
- Los tests crean apps con su propia configuración (otra base, otro reloj).

Uvicorn la levanta con:  uvicorn mavic.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mavic.api.error_handlers import register_error_handlers
from mavic.api.middleware import RequestContextMiddleware
from mavic.api.router import api_router
from mavic.core.clock import Clock, SystemClock
from mavic.core.config import Settings, get_settings
from mavic.core.db import Database
from mavic.core.logging import configure_logging
from mavic.modules.identity.api.login_throttle import LoginThrottle
from mavic.modules.voice.domain.call_gateway import CallGateway
from mavic.modules.voice.infrastructure.elevenlabs_calls import ElevenLabsCallGateway


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    clock: Clock | None = None,
    call_gateway: CallGateway | None = None,
) -> FastAPI:
    """Construye la app. Los parámetros opcionales permiten reemplazar piezas en tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    database = database or Database(settings.database_url.get_secret_value())
    clock = clock or SystemClock(settings.business_timezone)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Código antes del `yield`: al arrancar. Después: al apagar.
        yield
        database.dispose()

    app = FastAPI(
        title="Mavic API",
        version="0.1.0",
        lifespan=lifespan,
        # Swagger solo si está habilitado (en producción se apaga).
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # Objetos compartidos, disponibles para las dependencias (ver api/deps.py).
    app.state.settings = settings
    app.state.database = database
    app.state.clock = clock
    # Llamadas salientes: el cliente de ElevenLabs, si están las tres credenciales.
    app.state.call_gateway = call_gateway or _elevenlabs_gateway(settings)
    app.state.login_throttle = LoginThrottle(
        max_failures=settings.login_max_failures,
        window=timedelta(minutes=settings.login_lockout_minutes),
        clock=clock,
    )

    # Orden de middlewares: el último agregado es el primero en recibir el request.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # necesario para enviar la cookie de sesión
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)
    app.include_router(api_router)
    return app


def _elevenlabs_gateway(settings: Settings) -> CallGateway | None:
    if not (
        settings.elevenlabs_api_key
        and settings.elevenlabs_agent_id
        and settings.elevenlabs_phone_number_id
    ):
        return None
    return ElevenLabsCallGateway(
        api_key=settings.elevenlabs_api_key.get_secret_value(),
        agent_id=settings.elevenlabs_agent_id,
        phone_number_id=settings.elevenlabs_phone_number_id,
    )
