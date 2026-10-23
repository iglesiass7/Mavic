"""Filtros de las pantallas con el diseño de Rynx (etapa 7b).

Reloj de los tests: 16/10/2026. Cartera de FibraSur:
    Ana Torres    A-1  70.000,00   vence 10/09  vencida
                  A-2  50.000,50   vence 10/10  vencida
    Bruno Paz     B-1   5.000,00   vence 16/10  vence hoy
    Carla Ríos    C-1 900.000,00   vence 20/11  por vencer
    Diego Sosa    D-1  12.500,00   vence 01/09  vencida
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from mavic.core.db import Database
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from tests.conftest import AGENT_TOKEN
from tests.factories import invoice_row, logged_client, make_company, make_user, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def debtor(name: str, document: str, n: int) -> dict[str, str]:
    return {
        "debtor_name": name,
        "debtor_document": document,
        "debtor_phone": f"+54911555502{n:02d}",
        "debtor_email": f"{name.split()[0].lower()}@example.com",
    }


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    client = logged_client(app, "laura@fibrasur.com")
    ana, bruno = debtor("Ana Torres", "27987654", 1), debtor("Bruno Paz", "20111222", 2)
    carla, diego = debtor("Carla Ríos", "27333444", 3), debtor("Diego Sosa", "20555666", 4)
    rows = [
        invoice_row(
            external_id="A-1",
            description="Abono internet agosto",
            amount="70000",
            due_date="2026-09-10",
            **ana,
        ),
        invoice_row(
            external_id="A-2",
            description="Abono 100% fibra",
            amount="50000.50",
            due_date="2026-10-10",
            **ana,
        ),
        invoice_row(external_id="B-1", amount="5000", due_date="2026-10-16", **bruno),
        invoice_row(external_id="C-1", amount="900000", due_date="2026-11-20", **carla),
        invoice_row(external_id="D-1", amount="12500", due_date="2026-09-01", **diego),
    ]
    assert upload(client, rows).status_code == 201
    return client


def ids(response: Any) -> list[str]:
    return [item["external_id"] for item in response.json()["items"]]


# ---------------------------------------------------------------- facturas


def test_invoices_by_stage_like_the_three_groups_of_rynx(laura: TestClient) -> None:
    upcoming = laura.get("/invoices", params={"stage": "upcoming"})
    today = laura.get("/invoices", params={"stage": "due_today"})
    overdue = laura.get("/invoices", params={"stage": "overdue"})

    assert ids(upcoming) == ["C-1"]
    assert ids(today) == ["B-1"]
    assert ids(overdue) == ["D-1", "A-1", "A-2"]  # por vencimiento


def test_invoice_search_amount_range_and_sort(laura: TestClient) -> None:
    by_debtor = laura.get("/invoices", params={"q": "torres"})
    by_document = laura.get("/invoices", params={"q": "20555"})
    literal_percent = laura.get("/invoices", params={"q": "100%"})
    in_range = laura.get("/invoices", params={"min_amount": "10000", "max_amount": "70000"})
    by_amount = laura.get("/invoices", params={"sort": "-amount"})

    assert ids(by_debtor) == ["A-1", "A-2"]
    assert ids(by_document) == ["D-1"]
    assert ids(literal_percent) == ["A-2"]  # "%" se busca tal cual, no es comodín
    assert sorted(ids(in_range)) == ["A-1", "A-2", "D-1"]
    assert ids(by_amount) == ["C-1", "A-1", "A-2", "D-1", "B-1"]


def test_amount_max_ignores_the_amount_range_but_not_the_other_filters(laura: TestClient) -> None:
    overdue = laura.get("/invoices", params={"stage": "overdue", "max_amount": "100"})

    assert overdue.json()["total"] == 0
    assert overdue.json()["amount_max"] == "70000.00"  # el tope del filtro sigue siendo el real


# ---------------------------------------------------------------- casos


@pytest.fixture
def with_cases(laura: TestClient) -> TestClient:
    assert laura.post("/cases/generate").json()["cases_created"] == 2  # Ana y Diego
    return laura


def names(response: Any) -> list[str]:
    return [item["debtor"]["name"] for item in response.json()["items"]]


def test_cases_search_by_name_document_or_number(with_cases: TestClient) -> None:
    ana = with_cases.get("/cases", params={"q": "ana"}).json()["items"][0]

    assert names(with_cases.get("/cases", params={"q": "20555666"})) == ["Diego Sosa"]
    assert names(with_cases.get("/cases", params={"q": f"#{ana['number']}"})) == ["Ana Torres"]


def test_cases_amount_range_and_sorting(with_cases: TestClient) -> None:
    small = with_cases.get("/cases", params={"max_amount": "20000"})
    by_name_desc = with_cases.get("/cases", params={"sort": "-debtor"})

    assert names(small) == ["Diego Sosa"]
    assert small.json()["amount_max"] == "120000.50"
    assert names(by_name_desc) == ["Diego Sosa", "Ana Torres"]


def test_an_operator_can_escalate_a_case_to_a_person(
    app: FastAPI, with_cases: TestClient, database: Database, fibrasur: CompanyWithAdmin
) -> None:
    case = with_cases.get("/cases", params={"q": "ana"}).json()["items"][0]
    make_user(database, fibrasur, "pablo@fibrasur.com", UserRole.OPERATOR)
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)
    pablo = logged_client(app, "pablo@fibrasur.com")
    martin = logged_client(app, "martin@fibrasur.com")

    assert martin.post(f"/cases/{case['id']}/escalate").status_code == 403
    escalated = pablo.post(f"/cases/{case['id']}/escalate")
    again = pablo.post(f"/cases/{case['id']}/escalate")

    assert escalated.status_code == 200
    assert escalated.json()["status"] == "escalated"
    assert again.status_code == 409
    assert again.json()["code"] == "CASE_NOT_NEGOTIABLE"


# ---------------------------------------------------------------- conversaciones


def agent_call(app: FastAPI, case_number: int, conversation: str, name: str, **result: Any) -> None:
    agent = TestClient(app)
    agent.headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
    body = {"caso_id": str(case_number), "conversation_id": conversation}
    agent.post(
        "/agent/tools/obtener_contexto_del_caso_v2",
        json={**body, "nombre_consultado": name, "respuesta": "si"},
    )
    if result:
        agent.post("/agent/tools/registrar_resultado_v2", json={**body, **result})


def test_all_calls_of_the_company_with_their_case(
    app: FastAPI, with_cases: TestClient, database: Database
) -> None:
    ana = with_cases.get("/cases", params={"q": "ana"}).json()["items"][0]
    diego = with_cases.get("/cases", params={"q": "diego"}).json()["items"][0]
    agent_call(app, ana["number"], "conv_ana", "Ana Torres", resultado="CONTACTADO")
    agent_call(app, diego["number"], "conv_diego", "Diego Sosa")  # sin resultado todavía

    every = with_cases.get("/conversations").json()
    contacted = with_cases.get("/conversations", params={"outcome": "CONTACTADO"}).json()
    ongoing = with_cases.get("/conversations", params={"outcome": "ongoing"}).json()
    by_name = with_cases.get("/conversations", params={"q": "diego"}).json()
    assert every["total"] == 2
    [item] = contacted["items"]
    assert item["debtor_name"] == "Ana Torres"
    assert item["case_number"] == ana["number"]
    assert item["call"]["result"] == "CONTACTADO"
    assert [i["debtor_name"] for i in ongoing["items"]] == ["Diego Sosa"]
    assert [i["debtor_name"] for i in by_name["items"]] == ["Diego Sosa"]
    make_company(database, "Aguas del Sur", admin_email="elena@aguasdelsur.com")
    elena = logged_client(app, "elena@aguasdelsur.com")
    assert elena.get("/conversations").json()["total"] == 0  # cada empresa ve lo suyo


def test_the_day_filter_uses_argentine_time(
    app: FastAPI, with_cases: TestClient, database: Database
) -> None:
    """23:30 del 15/10 en Argentina ya es 16/10 en UTC: cuenta como llamada del 15."""
    ana = with_cases.get("/cases", params={"q": "ana"}).json()["items"][0]
    diego = with_cases.get("/cases", params={"q": "diego"}).json()["items"][0]
    agent_call(app, ana["number"], "conv_ana", "Ana Torres")
    agent_call(app, diego["number"], "conv_diego", "Diego Sosa")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE conversations SET created_at = CASE provider_conversation_id "
                "WHEN 'conv_ana' THEN TIMESTAMPTZ '2026-10-16 13:00+00' "
                "ELSE TIMESTAMPTZ '2026-10-15 23:30-03' END"
            )
        )

    def on(day: str) -> list[str]:
        items = with_cases.get("/conversations", params={"day": day}).json()["items"]
        return [item["debtor_name"] for item in items]

    assert on("2026-10-16") == ["Ana Torres"]
    assert on("2026-10-15") == ["Diego Sosa"]
