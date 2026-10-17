"""Fixtures compartidas por los tests.

Una fixture es algo que pytest prepara antes de un test y le pasa como
parámetro. Ejemplo: un test que declara `client` recibe un cliente HTTP listo.

Los tests que usan la base corren contra PostgreSQL REAL (no SQLite): el
proyecto usa tipos y bloqueos propios de PostgreSQL, y probar contra otro motor
da falsa confianza. La base de tests es `mavic_test`, separada de la de la app.

Aislamiento entre tests: el esquema se crea una vez por corrida, y después de
cada test que usa la base se vacían todas las tablas. Cada test arranca limpio.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from mavic.core.clock import FixedClock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.core.errors import ExternalServiceError
from mavic.main import create_app
from mavic.models import Base

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://mavic:mavic@localhost:5432/mavic_test"
)
BUSINESS_TZ = "America/Argentina/Buenos_Aires"

# Un instante fijo para todos los tests: 16/10/2026 15:00 UTC (12:00 en Argentina).
FIXED_NOW = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)


def _fail_or_skip(message: str) -> None:
    """En tu PC, sin base, el test se SALTEA con un aviso. En CI, FALLA."""
    if os.getenv("CI"):
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def _test_schema() -> Iterator[None]:
    """Crea las tablas en la base de tests, una sola vez por corrida."""
    database = Database(TEST_DATABASE_URL)
    try:
        database.ping()
    except ExternalServiceError as exc:
        database.dispose()
        _fail_or_skip(
            "No hay PostgreSQL de tests disponible. Levantalo con: docker compose up -d db "
            f"({type(exc).__name__})"
        )
    Base.metadata.drop_all(database.engine)
    Base.metadata.create_all(database.engine)
    yield
    database.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        docs_enabled=True,
        session_cookie_secure=False,  # el cliente de tests usa http://
        _env_file=None,  # ignora cualquier .env local
    )


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED_NOW, BUSINESS_TZ)


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    db = Database(settings.database_url.get_secret_value())
    yield db
    db.dispose()


@pytest.fixture
def require_db(_test_schema: None, database: Database) -> Iterator[Database]:
    """Para tests que usan la base. Al terminar, vacía todas las tablas."""
    yield database
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with database.engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def app(settings: Settings, database: Database, clock: FixedClock) -> FastAPI:
    return create_app(settings, database=database, clock=clock)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
