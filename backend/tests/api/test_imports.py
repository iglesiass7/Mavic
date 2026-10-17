"""CU-04 · Importación de facturas."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.db import Database
from mavic.modules.identity.domain.roles import UserRole
from tests.factories import (
    csv_file,
    invoice_row,
    logged_client,
    make_company,
    make_user,
    upload,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


@pytest.fixture
def pablo(app: FastAPI, database: Database) -> TestClient:
    """Operador de FibraSur con la sesión iniciada."""
    company = make_company(database, "FibraSur", admin_email="laura@fibrasur.com")
    make_user(database, company, "pablo@fibrasur.com", UserRole.OPERATOR)
    return logged_client(app, "pablo@fibrasur.com")


def _invoices(client: TestClient) -> list[dict[str, object]]:
    items: list[dict[str, object]] = client.get("/invoices").json()["items"]
    return items


def test_preview_reports_what_would_happen_without_writing(pablo: TestClient) -> None:
    response = upload(pablo, [invoice_row(), invoice_row(external_id="F-2")], preview=True)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert (body["debtors_created"], body["invoices_created"]) == (1, 2)
    assert body["import_id"] is None
    assert _invoices(pablo) == []  # no se guardó nada


def test_import_loads_debtors_and_invoices(pablo: TestClient) -> None:
    response = upload(pablo, [invoice_row(amount="18.500,50")])

    assert response.status_code == 201
    assert response.json()["import_id"] is not None
    invoice = _invoices(pablo)[0]
    assert invoice["amount"] == "18500.50"  # la plata viaja como texto exacto
    assert invoice["debtor_name"] == "Ana Torres"
    assert invoice["stage"] == "overdue"


def test_a_single_error_rejects_the_whole_file(pablo: TestClient) -> None:
    rows = [invoice_row(), invoice_row(external_id="F-2", debtor_phone="123")]

    response = upload(pablo, rows)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "IMPORT_HAS_ERRORS"
    assert body["report"]["errors"] == [
        {
            "row": 3,
            "column": "debtor_phone",
            "code": "INVALID_PHONE",
            "message": "El teléfono '123' no es válido.",
        }
    ]
    assert _invoices(pablo) == []  # todo o nada: tampoco se cargó la fila buena


def test_reimporting_the_same_file_changes_nothing(pablo: TestClient) -> None:
    upload(pablo, [invoice_row()])

    body = upload(pablo, [invoice_row()]).json()

    assert (body["invoices_created"], body["invoices_unchanged"]) == (0, 1)


def test_invoice_without_case_is_updated_on_reimport(pablo: TestClient) -> None:
    upload(pablo, [invoice_row(amount="1000")])

    body = upload(pablo, [invoice_row(amount="1200")]).json()

    assert body["invoices_updated"] == 1
    assert _invoices(pablo)[0]["amount"] == "1200.00"


def test_invoice_already_in_a_case_cannot_be_changed_by_an_import(pablo: TestClient) -> None:
    upload(pablo, [invoice_row(amount="1000")])
    pablo.post("/cases/generate")

    response = upload(pablo, [invoice_row(amount="500")])

    assert response.status_code == 422
    assert response.json()["report"]["errors"][0]["code"] == "INVOICE_IN_CASE"
    assert _invoices(pablo)[0]["amount"] == "1000.00"


def test_same_document_in_two_companies_are_two_different_debtors(
    app: FastAPI, database: Database, pablo: TestClient
) -> None:
    # En el original, la empresa B pisaba nombre y teléfono del deudor de la empresa A.
    make_company(database, "AguaNorte", admin_email="jefa@aguanorte.com")
    agua = logged_client(app, "jefa@aguanorte.com")
    upload(pablo, [invoice_row(debtor_name="Ana Torres")])

    upload(agua, [invoice_row(debtor_name="Ana B. Torres", debtor_phone="+5491155550199")])

    assert _invoices(pablo)[0]["debtor_name"] == "Ana Torres"
    assert _invoices(agua)[0]["debtor_name"] == "Ana B. Torres"
    assert len(_invoices(pablo)) == 1  # cada empresa ve solo sus facturas


def test_missing_columns_are_reported(pablo: TestClient) -> None:
    content = b"external_id,amount\nF-1,10\n"
    response = pablo.post("/imports", files={"file": ("f.csv", content, "text/csv")})
    assert response.status_code == 422
    assert response.json()["code"] == "MISSING_COLUMNS"


def test_files_over_the_size_limit_are_rejected(pablo: TestClient) -> None:
    content = csv_file([invoice_row()]) + b" " * (5 * 1024 * 1024)
    response = pablo.post("/imports", files={"file": ("f.csv", content, "text/csv")})
    assert response.status_code == 422
    assert response.json()["code"] == "FILE_TOO_LARGE"


def test_supervisor_can_see_but_not_import(app: FastAPI, database: Database) -> None:
    company = make_company(database, admin_email="laura@fibrasur.com")
    make_user(database, company, "martin@fibrasur.com", UserRole.SUPERVISOR)
    martin = logged_client(app, "martin@fibrasur.com")

    assert upload(martin, [invoice_row()]).status_code == 403
    assert martin.get("/invoices").status_code == 200
    assert martin.get("/imports").status_code == 200


def test_import_history_records_who_and_what(pablo: TestClient) -> None:
    upload(pablo, [invoice_row(), invoice_row(external_id="F-2")])
    me = pablo.get("/auth/me").json()["user"]

    history = pablo.get("/imports").json()

    assert len(history) == 1
    assert history[0]["user_id"] == me["id"]
    assert history[0]["filename"] == "facturas.csv"
    assert history[0]["invoices_created"] == 2


def test_template_has_the_required_columns(pablo: TestClient) -> None:
    response = pablo.get("/imports/template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    header = response.content.decode("utf-8-sig").splitlines()[0]
    assert header.startswith("external_id,description,debtor_name")
