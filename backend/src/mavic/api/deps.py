"""Dependencias de FastAPI compartidas por los routers.

Una "dependencia" es una función que FastAPI ejecuta antes del endpoint y cuyo
resultado le pasa como parámetro. Sirve para no repetir código en cada ruta:

    @router.get("/users")
    def list_users(session: SessionDep, actor: ActorDep): ...
                   └─ get_session()     └─ get_current_session() -> valida la cookie

Los objetos compartidos (base de datos, reloj, configuración) se guardan en
`app.state` al crear la app; las dependencias los leen de ahí. Así un test puede
crear una app con OTRA base o con un reloj fijo, sin tocar variables globales.

FastAPI ejecuta cada dependencia UNA vez por request aunque la pidan varias
funciones: la cookie se valida una sola vez.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.modules.identity.api.cookies import SESSION_COOKIE
from mavic.modules.identity.api.login_throttle import LoginThrottle
from mavic.modules.identity.application.auth import AuthenticatedSession, authenticate
from mavic.modules.identity.domain.actor import Actor


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_login_throttle(request: Request) -> LoginThrottle:
    throttle: LoginThrottle = request.app.state.login_throttle
    return throttle


def get_session(database: Annotated[Database, Depends(get_database)]) -> Iterator[Session]:
    """Una sesión de base de datos por request, que se cierra al terminar."""
    with database.session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SessionDep = Annotated[Session, Depends(get_session)]
LoginThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]


def get_current_session(
    request: Request, session: SessionDep, clock: ClockDep
) -> AuthenticatedSession:
    """Valida la cookie. Sin sesión válida, corta el request con 401."""
    return authenticate(session, token=request.cookies.get(SESSION_COOKIE), clock=clock)


def get_actor(
    current: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> Actor:
    return current.actor


CurrentSessionDep = Annotated[AuthenticatedSession, Depends(get_current_session)]
ActorDep = Annotated[Actor, Depends(get_actor)]
