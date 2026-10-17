"""Red de seguridad: ninguna ruta queda abierta sin querer.

Recorre TODAS las rutas que publica la API (según su documentación OpenAPI) y
las llama sin sesión. Las que no están en la lista pública tienen que responder
401. Si mañana alguien agrega un endpoint y se olvida de protegerlo, este test
falla. En el original, 62 de 71 endpoints estaban abiertos.
"""

import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.api.router import PUBLIC_PATHS


def _all_routes(app: FastAPI) -> list[tuple[str, str]]:
    routes = []
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            routes.append((method.upper(), path))
    return routes


def test_the_public_list_is_small_and_explicit() -> None:
    assert {"/health", "/health/ready", "/auth/login", "/auth/logout"} == PUBLIC_PATHS


def test_every_non_public_route_requires_a_session(app: FastAPI) -> None:
    client = TestClient(app)
    protected = [(m, p) for m, p in _all_routes(app) if p not in PUBLIC_PATHS]
    assert protected, "No se encontraron rutas protegidas: ¿cambió el router?"

    open_routes = []
    for method, path in protected:
        # Reemplaza {user_id}, {case_id}, etc. por un UUID cualquiera.
        url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
        response = client.request(method, url, json={})
        if response.status_code != 401:
            open_routes.append(f"{method} {path} -> {response.status_code}")

    assert not open_routes, "Rutas accesibles sin sesión:\n" + "\n".join(open_routes)


@pytest.mark.parametrize("path", sorted(PUBLIC_PATHS - {"/health/ready"}))
def test_public_routes_do_not_ask_for_a_session(app: FastAPI, path: str) -> None:
    client = TestClient(app)
    method = "GET" if path.startswith("/health") else "POST"
    response = client.request(method, path, json={})
    assert response.status_code != 401
