"""CU-06 · Configurar reglas de negociación."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.db import Database
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from tests.factories import logged_client, make_company, make_user, rule_body

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    """Administradora de FibraSur con la sesión iniciada."""
    return logged_client(app, "laura@fibrasur.com")


def test_admin_creates_and_lists_rules(laura: TestClient) -> None:
    response = laura.post("/negotiation-rules", json=rule_body(max_amount=500000))

    assert response.status_code == 201
    rule = response.json()
    assert rule["max_amount"] == "500000.00"  # la plata vuelve como texto exacto
    assert rule["max_debt_age_days"] == 59
    assert rule["max_invoice_count"] is None  # sin tope
    assert [r["name"] for r in laura.get("/negotiation-rules").json()] == ["Corto plazo"]


def test_overlapping_active_rules_are_rejected(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(name="Corto plazo"))  # 15 a 59 días

    response = laura.post(
        "/negotiation-rules",
        json=rule_body(name="Mora alta", min_debt_age_days=50, max_debt_age_days=None),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "RULE_OVERLAP"
    assert "Corto plazo" in body["detail"]


def test_rules_that_touch_but_do_not_overlap_are_fine(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(name="Corto plazo"))  # 15 a 59
    response = laura.post(
        "/negotiation-rules",
        json=rule_body(name="Mora alta", min_debt_age_days=60, max_debt_age_days=None),
    )
    assert response.status_code == 201


def test_an_inactive_rule_may_overlap_but_cannot_be_activated(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(name="Vigente"))
    draft = rule_body(name="Borrador", is_active=False)

    created = laura.post("/negotiation-rules", json=draft)
    assert created.status_code == 201

    activate = laura.put(
        f"/negotiation-rules/{created.json()['id']}", json={**draft, "is_active": True}
    )
    assert activate.status_code == 409
    assert activate.json()["code"] == "RULE_OVERLAP"


def test_updating_a_rule_does_not_collide_with_itself(laura: TestClient) -> None:
    rule = laura.post("/negotiation-rules", json=rule_body()).json()

    response = laura.put(f"/negotiation-rules/{rule['id']}", json=rule_body(discount_pct="12.5"))

    assert response.status_code == 200
    assert response.json()["discount_pct"] == "12.50"


def test_deactivating_a_rule(laura: TestClient) -> None:
    rule = laura.post("/negotiation-rules", json=rule_body()).json()
    response = laura.put(f"/negotiation-rules/{rule['id']}", json=rule_body(is_active=False))
    assert response.json()["is_active"] is False


def test_rule_names_are_unique_per_company_ignoring_case(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(name="Mora alta"))
    response = laura.post(
        "/negotiation-rules",
        json=rule_body(name="  MORA ALTA ", is_active=False),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RULE_NAME_TAKEN"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"min_debt_age_days": 60, "max_debt_age_days": 30}, "INVALID_RANGE"),
        ({"min_amount": "1000", "max_amount": "10"}, "INVALID_RANGE"),
        ({"discount_pct": "100"}, "INVALID_DISCOUNT"),
        ({"max_installments": 0}, "INVALID_INSTALLMENTS"),
        ({"payment_days": 0}, "INVALID_PAYMENT_DAYS"),
    ],
)
def test_invalid_rules_are_rejected_with_a_clear_code(
    laura: TestClient, overrides: dict[str, object], code: str
) -> None:
    response = laura.post("/negotiation-rules", json=rule_body(**overrides))
    assert response.status_code == 422
    assert response.json()["code"] == code


def test_malformed_values_are_rejected_before_reaching_the_rules(laura: TestClient) -> None:
    # Tres decimales en un monto, o un número que no entra en la base: error de formato.
    assert laura.post("/negotiation-rules", json=rule_body(max_amount="10.555")).status_code == 422
    assert laura.post("/negotiation-rules", json=rule_body(payment_days=10**12)).status_code == 422
    assert laura.post("/negotiation-rules", json=rule_body(name="   ")).status_code == 422


@pytest.mark.parametrize("role", [UserRole.OPERATOR, UserRole.SUPERVISOR])
def test_operator_and_supervisor_can_see_rules_but_not_change_them(
    app: FastAPI,
    database: Database,
    fibrasur: CompanyWithAdmin,
    laura: TestClient,
    role: UserRole,
) -> None:
    rule = laura.post("/negotiation-rules", json=rule_body()).json()
    make_user(database, fibrasur, "pablo@fibrasur.com", role)
    user = logged_client(app, "pablo@fibrasur.com")

    assert user.get("/negotiation-rules").status_code == 200
    assert user.post("/negotiation-rules", json=rule_body(name="X")).status_code == 403
    assert user.put(f"/negotiation-rules/{rule['id']}", json=rule_body()).status_code == 403


def test_rules_of_another_company_are_invisible(
    app: FastAPI, database: Database, laura: TestClient
) -> None:
    rule = laura.post("/negotiation-rules", json=rule_body()).json()
    make_company(database, "AguaNorte", admin_email="jefa@aguanorte.com")
    agua = logged_client(app, "jefa@aguanorte.com")

    assert agua.get("/negotiation-rules").json() == []
    response = agua.put(f"/negotiation-rules/{rule['id']}", json=rule_body())
    assert response.status_code == 404
    assert response.json()["code"] == "RULE_NOT_FOUND"
    # Y como son de empresas distintas, AguaNorte puede tener una regla igual.
    assert agua.post("/negotiation-rules", json=rule_body()).status_code == 201
