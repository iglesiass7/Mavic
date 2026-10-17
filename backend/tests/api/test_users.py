"""Gestión de usuarios: permisos por rol y aislamiento entre empresas."""

import pytest
from fastapi import FastAPI

from mavic.core.db import Database
from mavic.modules.identity.domain.roles import UserRole
from tests.factories import (
    PASSWORD,
    logged_client,
    make_company,
    make_platform_admin,
    make_user,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

NEW_USER = {
    "name": "Pablo Díaz",
    "email": "pablo@fibrasur.com",
    "password": PASSWORD,
    "role": "operator",
}


def test_admin_creates_a_user_in_their_own_company(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.post("/users", json=NEW_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["company_id"] == str(company.company.id)
    assert body["role"] == "operator"
    assert "password" not in body
    # El usuario nuevo puede iniciar sesión.
    logged_client(app, "pablo@fibrasur.com")


def test_admin_only_sees_users_of_their_company(app: FastAPI, database: Database) -> None:
    make_company(database, "FibraSur", admin_email="laura@fibrasur.com")
    make_company(database, "AguaNorte", admin_email="admin@aguanorte.com")
    laura = logged_client(app, "laura@fibrasur.com")

    emails = [user["email"] for user in laura.get("/users").json()]

    assert emails == ["laura@fibrasur.com"]


def test_admin_cannot_edit_a_user_of_another_company(app: FastAPI, database: Database) -> None:
    make_company(database, "FibraSur", admin_email="laura@fibrasur.com")
    other = make_company(database, "AguaNorte", admin_email="admin@aguanorte.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.patch(f"/users/{other.admin.id}", json={"is_active": False})

    # 404 y no 403: ni siquiera se confirma que ese usuario existe.
    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


@pytest.mark.parametrize("role", [UserRole.OPERATOR, UserRole.SUPERVISOR])
def test_non_admins_cannot_manage_users(app: FastAPI, database: Database, role: UserRole) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    make_user(database, company, "user@fibrasur.com", role)
    client = logged_client(app, "user@fibrasur.com")

    assert client.get("/users").status_code == 403
    assert client.post("/users", json=NEW_USER).status_code == 403


def test_platform_admin_cannot_manage_company_users(app: FastAPI, database: Database) -> None:
    make_platform_admin(database)
    owner = logged_client(app, "dueno@mavic-demo.com")
    assert owner.get("/users").status_code == 403


def test_duplicate_email_is_rejected(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.post("/users", json={**NEW_USER, "email": "LAURA@fibrasur.com"})

    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_ALREADY_REGISTERED"


def test_cannot_assign_the_platform_admin_role(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.post("/users", json={**NEW_USER, "role": "platform_admin"})

    assert response.status_code == 422


def test_unknown_fields_are_rejected_not_ignored(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    pablo = make_user(database, company, "pablo@fibrasur.com", UserRole.OPERATOR)
    laura = logged_client(app, "laura@fibrasur.com")

    # En el original, mandar company_id permitía mover un usuario a otra empresa.
    response = laura.patch(f"/users/{pablo.id}", json={"company_id": "otra"})

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "extra_forbidden"


def test_cannot_deactivate_the_last_active_admin(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.patch(f"/users/{company.admin.id}", json={"is_active": False})

    assert response.status_code == 409
    assert response.json()["code"] == "LAST_ACTIVE_ADMIN"


def test_cannot_demote_the_last_active_admin(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.patch(f"/users/{company.admin.id}", json={"role": "operator"})

    assert response.status_code == 409


def test_an_admin_can_be_removed_when_another_admin_remains(
    app: FastAPI, database: Database
) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    make_user(database, company, "sofia@fibrasur.com", UserRole.ADMIN)
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.patch(f"/users/{company.admin.id}", json={"role": "operator"})

    assert response.status_code == 200
    assert response.json()["role"] == "operator"


def test_deactivating_a_user_ends_their_open_sessions(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    pablo = make_user(database, company, "pablo@fibrasur.com", UserRole.OPERATOR)
    pablo_client = logged_client(app, "pablo@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    assert laura.patch(f"/users/{pablo.id}", json={"is_active": False}).status_code == 200

    assert pablo_client.get("/auth/me").status_code == 401


def test_role_change_takes_effect_on_the_next_request(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    pablo = make_user(database, company, "pablo@fibrasur.com", UserRole.OPERATOR)
    pablo_client = logged_client(app, "pablo@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")
    assert pablo_client.get("/users").status_code == 403

    laura.patch(f"/users/{pablo.id}", json={"role": "admin"})

    # Los permisos se leen de la base en cada request: no hace falta volver a entrar.
    assert pablo_client.get("/users").status_code == 200
