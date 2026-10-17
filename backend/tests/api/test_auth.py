"""Inicio y cierre de sesión, validación de la cookie y cambio de contraseña."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.clock import FixedClock
from mavic.core.db import Database
from mavic.modules.identity.domain.roles import UserRole
from tests.factories import PASSWORD, logged_client, make_company, make_user

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def _login(client: TestClient, email: str, password: str = PASSWORD) -> tuple[int, dict[str, Any]]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response.status_code, response.json() if response.content else {}


def test_login_sets_a_secure_session_cookie_and_returns_the_user(
    client: TestClient, database: Database
) -> None:
    make_company(database, admin_email="laura@fibrasur.com")

    response = client.post(
        "/auth/login", json={"email": "laura@fibrasur.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "laura@fibrasur.com"
    assert body["user"]["role"] == "admin"
    assert body["company"]["name"] == "FibraSur"
    assert "manage_users" in body["permissions"]
    assert "password_hash" not in response.text

    cookie = response.headers["set-cookie"].lower()
    assert "mavic_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_email_is_case_insensitive(client: TestClient, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    status, _ = _login(client, "  LAURA@FibraSur.com ")
    assert status == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(
    client: TestClient, database: Database
) -> None:
    make_company(database, admin_email="laura@fibrasur.com")

    status_wrong, body_wrong = _login(client, "laura@fibrasur.com", "otra-clave-mal")
    status_unknown, body_unknown = _login(client, "nadie@fibrasur.com", "otra-clave-mal")

    # No se puede usar el login para averiguar qué emails existen.
    assert status_wrong == status_unknown == 401
    assert body_wrong["code"] == body_unknown["code"] == "INVALID_CREDENTIALS"
    assert body_wrong["detail"] == body_unknown["detail"]


def test_inactive_user_cannot_log_in(app: FastAPI, client: TestClient, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    pablo = make_user(database, company, "pablo@fibrasur.com", UserRole.OPERATOR)
    laura = logged_client(app, "laura@fibrasur.com")
    laura.patch(f"/users/{pablo.id}", json={"is_active": False})

    status, body = _login(client, "pablo@fibrasur.com")

    assert status == 403
    assert body["code"] == "USER_INACTIVE"


def test_me_requires_a_session(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_me_returns_the_logged_user(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "laura@fibrasur.com"


def test_logout_revokes_the_session_on_the_server(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")
    stolen_cookie = laura.cookies["mavic_session"]

    assert laura.post("/auth/logout").status_code == 204

    # Aunque alguien haya copiado la cookie, después del logout ya no sirve.
    attacker = TestClient(app, cookies={"mavic_session": stolen_cookie})
    assert attacker.get("/auth/me").status_code == 401


def test_logout_without_session_is_harmless(client: TestClient) -> None:
    assert client.post("/auth/logout").status_code == 204


def test_session_expires_after_its_ttl(app: FastAPI, database: Database, clock: FixedClock) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    clock.advance(timedelta(hours=7, minutes=59))
    assert laura.get("/auth/me").status_code == 200

    clock.advance(timedelta(minutes=2))  # pasan las 8 horas
    response = laura.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_INVALID"


def test_garbage_cookie_is_rejected(app: FastAPI) -> None:
    client = TestClient(app, cookies={"mavic_session": "inventada"})
    assert client.get("/auth/me").status_code == 401


def test_login_is_blocked_after_too_many_failures(client: TestClient, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    for _ in range(5):
        status, _ = _login(client, "laura@fibrasur.com", "clave-incorrecta")
        assert status == 401

    # Ni siquiera la contraseña correcta entra mientras dura el bloqueo.
    response = client.post(
        "/auth/login", json={"email": "laura@fibrasur.com", "password": PASSWORD}
    )
    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_REQUESTS"
    assert int(response.headers["retry-after"]) > 0


def test_change_password_closes_other_sessions_but_keeps_the_current_one(
    app: FastAPI, database: Database
) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laptop = logged_client(app, "laura@fibrasur.com")
    phone = logged_client(app, "laura@fibrasur.com")

    response = laptop.put(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "una frase nueva y larga"},
    )

    assert response.status_code == 204
    assert laptop.get("/auth/me").status_code == 200
    assert phone.get("/auth/me").status_code == 401
    # La contraseña vieja ya no sirve; la nueva, sí.
    assert _login(TestClient(app), "laura@fibrasur.com")[0] == 401
    assert _login(TestClient(app), "laura@fibrasur.com", "una frase nueva y larga")[0] == 200


def test_change_password_requires_the_current_one(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.put(
        "/auth/password",
        json={"current_password": "no-es-esta", "new_password": "una frase nueva y larga"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_CURRENT_PASSWORD"
    assert laura.get("/auth/me").status_code == 200  # la sesión sigue abierta


def test_change_password_enforces_the_password_policy(app: FastAPI, database: Database) -> None:
    make_company(database, admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")

    response = laura.put(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "corta"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "PASSWORD_TOO_SHORT"
