"""El tablero (GET /dashboard): números calculados con los datos reales.

Escenario de FibraSur, con el reloj de los tests en el 16/10/2026:

    Ana     120.000,00  vence 10/09  (36 días)  ─┐
    Bruno    50.000,00  vence 01/07  (107 días)  ├─ se agrupan en 3 casos
             25.000,50  vence 01/08              │
    Carla    10.000,00  vence 10/10  (6 días)   ─┘
    Diego    30.000,00  vence HOY    ─┐ por vencer: no van a un caso
    Elsa     40.000,00  vence 20/11  ─┘
    Fede      5.000,00  vence 01/10  ── se carga DESPUÉS de generar: vencida sin caso

Y el agente:
    Ana    identidad OK ─► acepta el pago único (10 % de descuento: 108.000)  ─► acuerdo
    Carla  identidad OK ─► CONTACTADO                                         ─► contactado
    Bruno  dice que no es él ─► la llamada termina sin resultado
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.db import Database
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from tests.conftest import AGENT_TOKEN
from tests.factories import (
    invoice_row,
    logged_client,
    make_company,
    make_platform_admin,
    make_user,
    rule_body,
    upload,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def person(name: str, document: str, n: int) -> dict[str, str]:
    """Los datos de un deudor para invoice_row."""
    return {
        "debtor_name": name,
        "debtor_document": document,
        "debtor_phone": f"+54911555501{n:02d}",
        "debtor_email": f"{name.split()[0].lower()}@example.com",
    }


ANA = person("Ana Torres", "27987654", 1)
BRUNO = person("Bruno Paz", "20111222", 2)
CARLA = person("Carla Ríos", "27333444", 3)
DIEGO = person("Diego Sosa", "20555666", 4)
ELSA = person("Elsa Vera", "27777888", 5)
FEDE = person("Fede Luna", "20999000", 6)


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    return logged_client(app, "laura@fibrasur.com")


@pytest.fixture
def agent(app: FastAPI) -> TestClient:
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
    return client


def tool(agent: TestClient, name: str, **params: Any) -> Any:
    response = agent.post(f"/agent/tools/{name}", json=params)
    assert response.status_code == 200, response.text
    return response.json()


def case_number(laura: TestClient, debtor: str) -> str:
    items = laura.get("/cases").json()["items"]
    return str(next(i["number"] for i in items if i["debtor"]["name"] == debtor))


@pytest.fixture
def scenario(laura: TestClient, agent: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(name="Corto plazo"))
    rows = [
        invoice_row(external_id="A-1", amount="120000", due_date="2026-09-10", **ANA),
        invoice_row(external_id="B-1", amount="50000", due_date="2026-07-01", **BRUNO),
        invoice_row(external_id="B-2", amount="25000.50", due_date="2026-08-01", **BRUNO),
        invoice_row(external_id="C-1", amount="10000", due_date="2026-10-10", **CARLA),
        invoice_row(external_id="D-1", amount="30000", due_date="2026-10-16", **DIEGO),
        invoice_row(external_id="E-1", amount="40000", due_date="2026-11-20", **ELSA),
    ]
    assert upload(laura, rows).status_code == 201
    assert laura.post("/cases/generate").json()["cases_created"] == 3
    rows.append(invoice_row(external_id="F-1", amount="5000", due_date="2026-10-01", **FEDE))
    assert upload(laura, rows).status_code == 201

    # Ana: acuerdo de pago único
    ana = {"caso_id": case_number(laura, "Ana Torres"), "conversation_id": "conv_ana"}
    tool(
        agent, "obtener_contexto_del_caso_v2", **ana, nombre_consultado="Ana Torres", respuesta="sí"
    )
    tool(agent, "obtener_oferta_pago_unico_v2", **ana)
    tool(
        agent,
        "registrar_resultado_v2",
        **ana,
        resultado="ACUERDO",
        oferta_id="PAGO-UNICO",
        confirmacion_final=True,
        cantidad_desconocimientos=0,
    )
    # Carla: contactada, sin acuerdo
    carla = {"caso_id": case_number(laura, "Carla Ríos"), "conversation_id": "conv_carla"}
    tool(
        agent,
        "obtener_contexto_del_caso_v2",
        **carla,
        nombre_consultado="Carla Ríos",
        respuesta="sí",
    )
    tool(
        agent,
        "registrar_resultado_v2",
        **carla,
        resultado="CONTACTADO",
        oferta_id=None,
        confirmacion_final=False,
        cantidad_desconocimientos=0,
    )
    # Bruno: no es él; la llamada termina sin registrar resultado
    bruno = {"caso_id": case_number(laura, "Bruno Paz"), "conversation_id": "conv_bruno"}
    tool(
        agent,
        "obtener_contexto_del_caso_v2",
        **bruno,
        nombre_consultado="Bruno Paz",
        respuesta="no",
    )


def test_the_dashboard_adds_up_the_portfolio_and_the_agent(
    laura: TestClient, scenario: None
) -> None:
    body = laura.get("/dashboard").json()

    assert body["as_of"] == "2026-10-16"
    portfolio = body["portfolio"]
    assert portfolio["currency"] == "ARS"
    # Los 6 estados, siempre en el mismo orden y con 0 si no hay casos.
    assert portfolio["by_status"] == [
        {"key": "pending", "cases": 1, "amount": "75000.50"},  # Bruno
        {"key": "contacted", "cases": 1, "amount": "10000.00"},  # Carla
        {"key": "agreement", "cases": 1, "amount": "120000.00"},  # Ana
        {"key": "disputed", "cases": 0, "amount": "0.00"},
        {"key": "escalated", "cases": 0, "amount": "0.00"},
        {"key": "closed", "cases": 0, "amount": "0.00"},
    ]
    assert (portfolio["cases_total"], portfolio["amount_total"]) == (3, "205000.50")
    # En gestión = lo que el agente todavía puede negociar (Bruno y Carla).
    assert (portfolio["in_progress_cases"], portfolio["in_progress_amount"]) == (2, "85000.50")
    assert portfolio["in_progress_by_age"] == [
        {"key": "0_30", "cases": 1, "amount": "10000.00"},  # Carla, 6 días
        {"key": "31_60", "cases": 0, "amount": "0.00"},
        {"key": "61_90", "cases": 0, "amount": "0.00"},
        {"key": "91_plus", "cases": 1, "amount": "75000.50"},  # Bruno, 107 días
    ]
    assert (portfolio["unassigned_overdue_invoices"], portfolio["unassigned_overdue_amount"]) == (
        1,
        "5000.00",  # Fede
    )
    assert (portfolio["upcoming_invoices"], portfolio["upcoming_amount"]) == (2, "70000.00")

    agent = body["agent"]
    assert (agent["calls"], agent["identity_verified"]) == (3, 2)
    assert agent["calls_by_result"] == {
        "CONTACTADO": 1,
        "DESCONOCIMIENTO": 0,
        "ACUERDO": 1,
        "DERIVACION_HUMANA": 0,
    }
    assert agent["calls_without_result"] == 1  # Bruno
    assert agent["last_call_at"] is not None
    assert (agent["agreements"], agent["agreements_single_payment"]) == (1, 1)
    assert agent["agreements_installments"] == 0
    assert (agent["agreed_original_amount"], agent["agreed_amount"]) == ("120000.00", "108000.00")


def test_a_new_company_sees_zeros_not_an_error(laura: TestClient) -> None:
    body = laura.get("/dashboard").json()

    portfolio, agent = body["portfolio"], body["agent"]
    assert portfolio["cases_total"] == 0
    assert portfolio["amount_total"] == "0.00"
    assert [b["key"] for b in portfolio["by_status"]] == [
        "pending",
        "contacted",
        "agreement",
        "disputed",
        "escalated",
        "closed",
    ]
    assert [b["key"] for b in portfolio["in_progress_by_age"]] == [
        "0_30",
        "31_60",
        "61_90",
        "91_plus",
    ]
    assert agent["calls"] == 0
    assert agent["last_call_at"] is None
    assert agent["agreed_amount"] == "0.00"


def test_each_company_only_counts_its_own_data(
    app: FastAPI, database: Database, laura: TestClient, scenario: None
) -> None:
    make_company(database, "Aguas del Sur", admin_email="elena@aguasdelsur.com")
    elena = logged_client(app, "elena@aguasdelsur.com")

    body = elena.get("/dashboard").json()

    assert body["portfolio"]["cases_total"] == 0
    assert body["portfolio"]["unassigned_overdue_invoices"] == 0
    assert body["agent"]["calls"] == 0


@pytest.mark.parametrize("role", [UserRole.OPERATOR, UserRole.SUPERVISOR])
def test_every_company_role_can_see_the_dashboard(
    app: FastAPI, database: Database, fibrasur: CompanyWithAdmin, role: UserRole
) -> None:
    make_user(database, fibrasur, f"{role.value}@fibrasur.com", role)
    client = logged_client(app, f"{role.value}@fibrasur.com")

    assert client.get("/dashboard").status_code == 200


def test_the_platform_owner_has_no_company_dashboard(app: FastAPI, database: Database) -> None:
    make_platform_admin(database)
    owner = logged_client(app, "dueno@mavic-demo.com")

    assert owner.get("/dashboard").status_code == 403
