"""Alta de empresas cliente por el dueño de la plataforma."""

from typing import Any

import pytest
from fastapi import FastAPI

from mavic.core.db import Database
from tests.factories import PASSWORD, logged_client, make_company, make_platform_admin

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def _payload(
    name: str = "AguaNorte", email: str = "jefa@aguanorte.com", password: str = PASSWORD
) -> dict[str, Any]:
    return {"name": name, "admin": {"name": "Jefa", "email": email, "password": password}}


def test_platform_admin_creates_a_company_with_its_first_admin(
    app: FastAPI, database: Database
) -> None:
    make_platform_admin(database)
    owner = logged_client(app, "dueno@mavic-demo.com")

    response = owner.post("/platform/companies", json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["company"]["name"] == "AguaNorte"
    assert body["admin"]["role"] == "admin"
    assert body["admin"]["company_id"] == body["company"]["id"]
    # La nueva administradora ya puede entrar.
    logged_client(app, "jefa@aguanorte.com")


def test_company_names_are_unique_ignoring_case(app: FastAPI, database: Database) -> None:
    make_platform_admin(database)
    make_company(database, "FibraSur")
    owner = logged_client(app, "dueno@mavic-demo.com")

    response = owner.post("/platform/companies", json=_payload(name="FIBRASUR"))

    assert response.status_code == 409
    assert response.json()["code"] == "COMPANY_NAME_TAKEN"


def test_company_is_not_created_if_its_admin_is_invalid(app: FastAPI, database: Database) -> None:
    make_platform_admin(database)
    owner = logged_client(app, "dueno@mavic-demo.com")

    response = owner.post("/platform/companies", json=_payload(password="corta"))

    assert response.status_code == 422
    # Todo o nada: no quedó una empresa sin administrador.
    assert owner.get("/platform/companies").json() == []


def test_company_admins_cannot_create_companies(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    assert laura.post("/platform/companies", json=_payload()).status_code == 403
    assert laura.get("/platform/companies").status_code == 403
