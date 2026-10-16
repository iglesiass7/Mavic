"""Dependencias de FastAPI compartidas por los routers.

Una "dependencia" es una función que FastAPI ejecuta antes del endpoint y cuyo
resultado le pasa como parámetro. Sirve para no repetir código en cada ruta:

    @router.get("/cases")
    def list_cases(session: SessionDep): ...   # FastAPI llama a get_session()

Los objetos compartidos (base de datos, reloj, configuración) se guardan en
`app.state` al crear la app; las dependencias los leen de ahí. Así un test puede
crear una app con OTRA base o con un reloj fijo, sin tocar variables globales.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.config import Settings
from mavic.core.db import Database


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_session(database: Annotated[Database, Depends(get_database)]) -> Iterator[Session]:
    """Una sesión por request, que se cierra al terminar el request."""
    with database.session() as session:
        yield session


# Alias para escribir menos en los endpoints: `session: SessionDep`.
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SessionDep = Annotated[Session, Depends(get_session)]
