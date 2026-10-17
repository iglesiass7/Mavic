"""Acceso a la base de datos.

Problema que resuelve: en el original el motor de base de datos se creaba al
IMPORTAR el módulo. Con solo hacer `import`, la app exigía variables reales, y
los tests no podían usar otra base.

Acá `Database` se crea explícitamente al armar la app (ver `mavic.main`), con la
URL que corresponda: la de desarrollo, la de tests o la de producción.

Conceptos (SQLAlchemy 2):
- Engine: administra el pool de conexiones a PostgreSQL. Uno por aplicación.
- Session: "conversación" con la base dentro de un request. Agrupa lecturas y
  escrituras y las confirma juntas (commit) o las descarta (rollback).
- Base: clase madre de todas las tablas. `Base.metadata` es lo que Alembic
  compara para generar migraciones.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, MetaData, create_engine, func, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from mavic.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)

# Convención de nombres para índices y restricciones. Sin esto, PostgreSQL
# inventa nombres y las migraciones que las borran o modifican se vuelven frágiles.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base de todos los modelos ORM (tablas)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Columnas de auditoría que llevan casi todas las tablas.

    `timestamptz` (DateTime con zona horaria): PostgreSQL guarda el instante en
    UTC y no hay ambigüedad. El sistema original guardaba fechas sin zona y
    terminó mezclando hora argentina con UTC.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Database:
    """Agrupa el engine y la fábrica de sesiones de una aplicación."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: Engine = create_engine(
            url,
            echo=echo,
            pool_pre_ping=True,  # descarta conexiones muertas antes de usarlas
            connect_args={"connect_timeout": 5},  # no esperar para siempre
        )
        # expire_on_commit=False: después del commit los objetos se pueden seguir
        # leyendo (por ejemplo, para armar la respuesta HTTP).
        self._session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Abre una sesión y la cierra al final, pase lo que pase.

        La sesión NO hace commit sola. Regla del proyecto: el caso de uso
        (capa application) llama a `session.commit()` una vez, al final. Si algo
        falla antes, la sesión se cierra sin commit y PostgreSQL descarta todo:
        la operación queda completa o no queda nada (atomicidad).
        """
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def ping(self) -> None:
        """Verifica que la base responda.

        Si no responde, lanza un ExternalServiceError (error de la app) en vez de
        la excepción técnica de SQLAlchemy: quien llama no necesita conocer la
        librería de base de datos.
        """
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.warning("La base de datos no responde: %s", type(exc).__name__)
            raise ExternalServiceError(
                "La base de datos no está disponible.", service="database"
            ) from exc

    def dispose(self) -> None:
        """Cierra todas las conexiones del pool (al apagar la app)."""
        self.engine.dispose()
