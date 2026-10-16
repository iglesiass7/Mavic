"""Fixtures compartidas por los tests.

Una fixture es algo que pytest prepara antes de un test y le pasa como
parámetro. Ejemplo: un test que declara `client` recibe un cliente HTTP listo.

Los tests que usan la base corren contra PostgreSQL REAL (no SQLite): el
proyecto usa tipos y bloqueos propios de PostgreSQL, y probar contra otro motor
da falsa confianza. La base de tests es `mavic_test`, separada de la de la app.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from mavic.core.clock import FixedClock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://mavic:mavic@localhost:5432/mavic_test"
)
BUSINESS_TZ = "America/Argentina/Buenos_Aires"

# Un instante fijo para todos los tests: 16/10/2026 15:00 UTC (12:00 en Argentina).
FIXED_NOW = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        docs_enabled=True,
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
def app(settings: Settings, database: Database, clock: FixedClock) -> FastAPI:
    return create_app(settings, database=database, clock=clock)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def require_db(database: Database) -> Database:
    """Para tests marcados con @pytest.mark.db: necesitan PostgreSQL levantado.

    En tu PC, si la base no está levantada, el test se SALTEA con un aviso claro.
    En CI (variable CI=true) FALLA: ahí la base siempre tiene que estar.
    """
    try:
        database.ping()
    except OperationalError as exc:
        message = "No hay PostgreSQL de tests disponible. Levantalo con: docker compose up -d db"
        if os.getenv("CI"):
            pytest.fail(message)
        pytest.skip(f"{message} ({type(exc).__name__})")
    return database
