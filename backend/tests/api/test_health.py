import pytest
from fastapi.testclient import TestClient

from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app


def test_health_is_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.db
def test_readiness_is_ok_when_database_responds(client: TestClient, require_db: Database) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_503_with_common_error_format_when_database_is_down(
    settings: Settings,
) -> None:
    # Una base que no existe: puerto 1 de localhost, la conexión se rechaza al instante.
    broken = Database("postgresql+psycopg://mavic:mavic@127.0.0.1:1/nada")
    app = create_app(settings, database=broken)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "EXTERNAL_SERVICE_ERROR"
    assert body["detail"] == "La base de datos no está disponible."
    # No se filtran detalles técnicos (host, driver, traza).
    assert "127.0.0.1" not in response.text
    assert "psycopg" not in response.text.lower()
