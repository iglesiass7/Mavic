"""CU-05 · Generar casos a partir de facturas vencidas, y consultarlos."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from mavic.core.db import Database
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.portfolio.infrastructure.orm import CaseModel
from tests.factories import invoice_row, logged_client, make_company, make_user, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

# Reloj de los tests: hoy es 16/10/2026.
ANA = {"debtor_name": "Ana Torres", "debtor_document": "27987654"}
RICARDO = {
    "debtor_name": "Ricardo Pérez",
    "debtor_document": "20123456",
    "debtor_phone": "+5491155550101",
    "debtor_email": "ricardo@example.com",
}


@pytest.fixture
def pablo(app: FastAPI, database: Database) -> TestClient:
    company = make_company(database, "FibraSur", admin_email="laura@fibrasur.com")
    make_user(database, company, "pablo@fibrasur.com", UserRole.OPERATOR)
    return logged_client(app, "pablo@fibrasur.com")


def test_overdue_invoices_are_grouped_into_one_case_per_debtor(pablo: TestClient) -> None:
    upload(
        pablo,
        [
            invoice_row(external_id="A-1", due_date="2026-09-10", amount="100", **ANA),
            invoice_row(external_id="A-2", due_date="2026-10-10", amount="250.50", **ANA),
            invoice_row(external_id="R-1", due_date="2026-08-01", amount="300", **RICARDO),
            invoice_row(external_id="R-2", due_date="2026-11-10", amount="999", **RICARDO),
        ],
    )

    result = pablo.post("/cases/generate").json()

    assert result == {"cases_created": 2, "cases_updated": 0, "invoices_assigned": 3}
    cases = pablo.get("/cases").json()["items"]
    by_name = {c["debtor"]["name"]: c for c in cases}
    assert by_name["Ana Torres"]["invoice_count"] == 2
    assert by_name["Ana Torres"]["total_amount"] == "350.50"
    assert by_name["Ana Torres"]["debt_age_days"] == 36  # desde el 10/09
    # R-2 todavía no vence: no entra en ningún caso.
    assert by_name["Ricardo Pérez"]["invoice_count"] == 1


def test_generating_twice_creates_nothing_the_second_time(pablo: TestClient) -> None:
    upload(pablo, [invoice_row(**ANA)])
    pablo.post("/cases/generate")

    second = pablo.post("/cases/generate").json()

    assert second == {"cases_created": 0, "cases_updated": 0, "invoices_assigned": 0}
    assert pablo.get("/cases").json()["total"] == 1


def test_new_overdue_invoices_join_the_pending_case(pablo: TestClient) -> None:
    upload(pablo, [invoice_row(external_id="A-1", due_date="2026-10-10", **ANA)])
    pablo.post("/cases/generate")
    # Más tarde llega otra factura vencida del mismo deudor.
    upload(pablo, [invoice_row(external_id="A-2", due_date="2026-10-12", **ANA)])

    result = pablo.post("/cases/generate").json()

    assert result == {"cases_created": 0, "cases_updated": 1, "invoices_assigned": 1}
    assert pablo.get("/cases").json()["items"][0]["invoice_count"] == 2


def test_a_case_already_contacted_does_not_receive_new_invoices(
    pablo: TestClient, database: Database
) -> None:
    upload(pablo, [invoice_row(external_id="A-1", **ANA)])
    pablo.post("/cases/generate")
    with database.session() as session:  # simula que el agente ya llamó
        session.execute(update(CaseModel).values(status=CaseStatus.CONTACTED))
        session.commit()
    upload(pablo, [invoice_row(external_id="A-1", **ANA), invoice_row(external_id="A-2", **ANA)])

    result = pablo.post("/cases/generate").json()

    assert result["cases_created"] == 1  # caso nuevo; el contactado queda como estaba
    statuses = sorted(c["status"] for c in pablo.get("/cases").json()["items"])
    assert statuses == ["contacted", "pending"]


def test_case_detail_includes_debtor_and_invoices(pablo: TestClient) -> None:
    upload(pablo, [invoice_row(external_id="A-1", **ANA), invoice_row(external_id="A-2", **ANA)])
    pablo.post("/cases/generate")
    case_id = pablo.get("/cases").json()["items"][0]["id"]

    detail = pablo.get(f"/cases/{case_id}").json()

    assert detail["debtor"]["phone"] == "+5491155550102"
    assert [i["external_id"] for i in detail["invoices"]] == ["A-1", "A-2"]
    assert all(i["case_number"] == detail["number"] for i in detail["invoices"])


def test_cases_of_another_company_are_invisible(
    app: FastAPI, database: Database, pablo: TestClient
) -> None:
    upload(pablo, [invoice_row(**ANA)])
    pablo.post("/cases/generate")
    case_id = pablo.get("/cases").json()["items"][0]["id"]
    make_company(database, "AguaNorte", admin_email="jefa@aguanorte.com")
    agua = logged_client(app, "jefa@aguanorte.com")

    assert agua.get("/cases").json()["total"] == 0
    response = agua.get(f"/cases/{case_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "CASE_NOT_FOUND"


def test_cases_can_be_sorted_filtered_and_paginated(pablo: TestClient) -> None:
    upload(
        pablo,
        [
            invoice_row(external_id="A-1", amount="100", due_date="2026-10-01", **ANA),
            invoice_row(external_id="R-1", amount="900", due_date="2026-09-01", **RICARDO),
        ],
    )
    pablo.post("/cases/generate")

    by_amount = pablo.get("/cases", params={"sort": "highest_amount", "limit": 1}).json()
    assert by_amount["total"] == 2
    assert [c["debtor"]["name"] for c in by_amount["items"]] == ["Ricardo Pérez"]

    second_page = pablo.get("/cases", params={"sort": "highest_amount", "limit": 1, "offset": 1})
    assert [c["debtor"]["name"] for c in second_page.json()["items"]] == ["Ana Torres"]

    assert pablo.get("/cases", params={"status": "agreement"}).json()["total"] == 0
    assert pablo.get("/cases", params={"limit": 500}).status_code == 422  # máximo 100


def test_invoice_list_filters(pablo: TestClient) -> None:
    upload(
        pablo,
        [
            invoice_row(external_id="A-1", due_date="2026-09-10", **ANA),
            invoice_row(external_id="A-2", due_date="2026-10-16", **ANA),  # vence hoy
            invoice_row(external_id="A-3", due_date="2026-12-10", **ANA),
        ],
    )
    pablo.post("/cases/generate")

    def ids(**params: str) -> list[str]:
        items = pablo.get("/invoices", params=params).json()["items"]
        return [i["external_id"] for i in items]

    assert ids() == ["A-1", "A-2", "A-3"]
    assert ids(in_case="true") == ["A-1"]
    assert ids(in_case="false") == ["A-2", "A-3"]
    assert ids(overdue_only="true") == ["A-1"]
    stages = [i["stage"] for i in pablo.get("/invoices").json()["items"]]
    assert stages == ["overdue", "due_today", "upcoming"]
