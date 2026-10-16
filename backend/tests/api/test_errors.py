"""El formato de error es el mismo para cualquier tipo de falla.

Se agregan rutas de prueba a la app que lanzan cada tipo de error, y se
comprueba qué recibe el cliente.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.errors import (
    BusinessRuleViolationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
)


@pytest.fixture
def error_client(app: FastAPI) -> Iterator[TestClient]:
    @app.get("/_test/not-found")
    def not_found() -> None:
        raise NotFoundError("El caso no existe.", code="CASE_NOT_FOUND")

    @app.get("/_test/conflict")
    def conflict() -> None:
        raise ConflictError("Ya existe un acuerdo pendiente.")

    @app.get("/_test/rule")
    def rule() -> None:
        raise BusinessRuleViolationError("El descuento supera el máximo permitido.")

    @app.get("/_test/forbidden")
    def forbidden() -> None:
        raise PermissionDeniedError()

    @app.get("/_test/external")
    def external() -> None:
        raise ExternalServiceError("El proveedor de voz no responde.", service="voice")

    @app.get("/_test/crash")
    def crash() -> None:
        raise RuntimeError("detalle interno con password=supersecreta")

    @app.get("/_test/validate")
    def validate(amount: int) -> dict[str, int]:
        return {"amount": amount}

    # raise_server_exceptions=False: queremos ver la respuesta 500, no la excepción.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/_test/not-found", 404, "CASE_NOT_FOUND"),
        ("/_test/conflict", 409, "CONFLICT"),
        ("/_test/rule", 422, "BUSINESS_RULE_VIOLATION"),
        ("/_test/forbidden", 403, "PERMISSION_DENIED"),
        ("/_test/external", 503, "EXTERNAL_SERVICE_ERROR"),
    ],
)
def test_app_errors_map_to_http_status_and_stable_code(
    error_client: TestClient, path: str, status: int, code: str
) -> None:
    response = error_client.get(path)
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["detail"]
    assert body["request_id"] == response.headers["x-request-id"]


def test_unexpected_error_returns_generic_500_without_internal_details(
    error_client: TestClient,
) -> None:
    response = error_client.get("/_test/crash")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["detail"] == "Ocurrió un error inesperado."
    assert "supersecreta" not in response.text
    assert "RuntimeError" not in response.text


def test_validation_error_lists_the_invalid_fields(error_client: TestClient) -> None:
    response = error_client.get("/_test/validate", params={"amount": "mucho"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"][0]["field"] == "query.amount"


def test_unknown_route_uses_the_same_error_format(client: TestClient) -> None:
    response = client.get("/no-existe")
    assert response.status_code == 404
    assert response.json()["code"] == "ROUTE_NOT_FOUND"


def test_valid_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "pedido-12345678"})
    assert response.headers["x-request-id"] == "pedido-12345678"


def test_suspicious_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert response.headers["x-request-id"] != "<script>alert(1)</script>"
    assert len(response.headers["x-request-id"]) == 32
