"""CU-07 · Calcular las ofertas de un caso (lo que después le pide el agente de voz)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from mavic.core.db import Database
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.portfolio.infrastructure.orm import CaseModel
from tests.factories import (
    invoice_row,
    logged_client,
    make_company,
    make_user,
    rule_body,
    upload,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

# Reloj de los tests: hoy es 16/10/2026.


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    return logged_client(app, "laura@fibrasur.com")


def _case_with(client: TestClient, rows: list[dict[str, str]]) -> str:
    """Importa las facturas, genera los casos y devuelve el id del primero."""
    assert upload(client, rows).status_code == 201
    client.post("/cases/generate")
    case_id: str = client.get("/cases").json()["items"][0]["id"]
    return case_id


def test_case_gets_both_offers_from_its_rule(laura: TestClient) -> None:
    # 120.000 con 36 días de atraso (vence el 10/09) -> regla de 15 a 59 días.
    laura.post("/negotiation-rules", json=rule_body(name="Corto plazo"))
    case_id = _case_with(laura, [invoice_row(amount="120000", due_date="2026-09-10")])

    body = laura.get(f"/cases/{case_id}/offers").json()

    assert body["has_offer"] is True
    assert body["reason"] is None
    assert body["rule"]["name"] == "Corto plazo"
    assert (body["total_amount"], body["debt_age_days"], body["currency"]) == (
        "120000.00",
        36,
        "ARS",
    )
    assert body["single_payment"] == {
        "offer_id": "PAGO-UNICO",
        "original_amount": "120000.00",
        "discount_pct": "10.00",
        "discount_amount": "12000.00",
        "total_amount": "108000.00",
        "pay_by": "2026-10-21",
    }
    plan = body["installments"]
    assert plan["offer_id"] == "CUOTAS-3-SIN-INTERES"
    assert plan["installment_amount"] == "40000.00"
    assert [i["due_date"] for i in plan["schedule"]] == ["2026-10-21", "2026-11-21", "2026-12-21"]


def test_the_rule_is_chosen_by_debt_age(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(name="Corto plazo"))  # 15 a 59 días
    laura.post(
        "/negotiation-rules",
        json=rule_body(
            name="Mora alta",
            min_debt_age_days=60,
            max_debt_age_days=None,
            max_installments=6,
            interest_pct="12",
        ),
    )
    case_id = _case_with(laura, [invoice_row(amount="56900", due_date="2026-08-10")])  # 67 días

    body = laura.get(f"/cases/{case_id}/offers").json()

    assert body["rule"]["name"] == "Mora alta"
    assert body["installments"]["offer_id"] == "CUOTAS-6-CON-INTERES"
    assert body["installments"]["total_amount"] == "63728.00"


def test_a_rule_with_one_installment_only_offers_single_payment(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(max_installments=1, discount_pct="0"))
    case_id = _case_with(laura, [invoice_row(due_date="2026-09-10")])

    body = laura.get(f"/cases/{case_id}/offers").json()

    assert body["single_payment"]["total_amount"] == "1000.00"
    assert body["installments"] is None


def test_without_a_matching_rule_there_is_no_offer(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(min_debt_age_days=60, max_debt_age_days=None))
    case_id = _case_with(laura, [invoice_row(due_date="2026-09-10")])  # 36 días

    body = laura.get(f"/cases/{case_id}/offers").json()

    assert body["has_offer"] is False
    assert body["reason"] == "NO_MATCHING_RULE"
    assert body["rule"] is None
    assert body["single_payment"] is None


def test_inactive_rules_are_ignored(laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(is_active=False))
    case_id = _case_with(laura, [invoice_row(due_date="2026-09-10")])
    assert laura.get(f"/cases/{case_id}/offers").json()["reason"] == "NO_MATCHING_RULE"


def test_a_case_with_a_result_is_not_negotiable(laura: TestClient, database: Database) -> None:
    laura.post("/negotiation-rules", json=rule_body())
    case_id = _case_with(laura, [invoice_row(due_date="2026-09-10")])
    with database.session() as session:  # simula que ya hubo un acuerdo
        session.execute(update(CaseModel).values(status=CaseStatus.AGREEMENT))
        session.commit()

    body = laura.get(f"/cases/{case_id}/offers").json()

    assert body["has_offer"] is False
    assert body["reason"] == "CASE_NOT_NEGOTIABLE"


def test_supervisor_can_see_offers(
    app: FastAPI, database: Database, fibrasur: CompanyWithAdmin, laura: TestClient
) -> None:
    laura.post("/negotiation-rules", json=rule_body())
    case_id = _case_with(laura, [invoice_row(due_date="2026-09-10")])
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)

    martin = logged_client(app, "martin@fibrasur.com")

    assert martin.get(f"/cases/{case_id}/offers").json()["has_offer"] is True


def test_offers_use_only_the_rules_of_the_case_company(
    app: FastAPI, database: Database, laura: TestClient
) -> None:
    case_id = _case_with(laura, [invoice_row(due_date="2026-09-10")])
    make_company(database, "AguaNorte", admin_email="jefa@aguanorte.com")
    agua = logged_client(app, "jefa@aguanorte.com")
    agua.post("/negotiation-rules", json=rule_body())  # regla de OTRA empresa

    assert laura.get(f"/cases/{case_id}/offers").json()["reason"] == "NO_MATCHING_RULE"
    response = agua.get(f"/cases/{case_id}/offers")
    assert response.status_code == 404
    assert response.json()["code"] == "CASE_NOT_FOUND"
