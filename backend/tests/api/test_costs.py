"""Medidor de costos (ADR-039): uso real del mes por las tarifas de la empresa.

Reloj de los tests: 16/10/2026. Octubre tiene 31 días, así que la proyección a
fin de mes es lo gastado × 31 / 16.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.clock import FixedClock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from tests.api.test_notices import FakeSenders, stage_body
from tests.api.test_outbound_calls import FakeGateway, call_settings, case_of, webhook
from tests.factories import invoice_row, logged_client, make_company, make_user, rule_body, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

RATES = {
    "currency": "USD",
    "call_minute": "0.12",
    "email": "0.001",
    "whatsapp": "0.05",
    "monthly_budget": "10",
}


@pytest.fixture
def app(settings: Settings, database: Database, clock: FixedClock) -> FastAPI:
    return create_app(
        call_settings(settings),
        database=database,
        clock=clock,
        call_gateway=FakeGateway(),
        notice_senders=FakeSenders(),
    )


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    return logged_client(app, "laura@fibrasur.com")


def concepts(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["concept"]: c for c in body["concepts"]}


def test_without_rates_everything_costs_zero_and_says_so(laura: TestClient) -> None:
    body = laura.get("/costs").json()

    assert body["month"] == "2026-10"
    assert body["rates_configured"] is False
    assert body["total"] == "0.00"
    assert body["budget_status"] == "no_budget"
    assert len(body["daily"]) == 31


def test_calls_and_notices_are_priced_with_the_company_rates(
    laura: TestClient, clock: FixedClock
) -> None:
    assert laura.put("/cost-rates", json=RATES).status_code == 200
    # Una llamada de 95 segundos (la duración que trae el webhook de prueba).
    laura.post("/negotiation-rules", json=rule_body())
    upload(
        laura,
        [invoice_row(external_id="F-1"), invoice_row(external_id="F-2", due_date="2026-10-18")],
    )
    laura.post("/cases/generate")
    started = laura.post(f"/cases/{case_of(laura, 'Ana Torres')['id']}/calls").json()
    assert (
        webhook(laura, clock, conversation_id=started["provider_conversation_id"]).status_code
        == 200
    )
    # Un email preventivo (F-2 vence el 18/10).
    laura.put("/notice-settings/preventive", json=stage_body())
    assert laura.post("/notices/send", json={"stage": "preventive"}).json()["sent"] == 1

    body = laura.get("/costs").json()

    by = concepts(body)
    assert by["calls"]["count"] == 1
    assert (
        by["calls"]["quantity"] == "1.58"
    )  # minutos, para mostrar (el costo usa los segundos exactos)
    assert by["calls"]["cost"] == "0.19"  # 95 s = 1,5833 min × 0,12
    assert by["email"]["count"] == 1
    assert by["email"]["cost"] == "0.00"  # 0,001: menos de un centavo
    assert by["whatsapp"]["cost"] == "0.00"
    assert body["total"] == "0.19"
    assert body["projected_total"] == "0.37"  # 0,19 × 31 / 16
    assert body["budget_status"] == "ok"
    assert body["daily"][15] == {"day": "2026-10-16", "cost": "0.19"}


def test_another_month_shows_nothing_from_october(laura: TestClient) -> None:
    body = laura.get("/costs", params={"month": "2026-09"}).json()

    assert body["month"] == "2026-09"
    assert body["days_counted"] == 30  # ya pasó entero: la proyección es lo gastado
    assert laura.get("/costs", params={"month": "2026-13"}).status_code == 422


def test_changing_rates_is_audited(laura: TestClient) -> None:
    laura.put("/cost-rates", json=RATES)
    laura.put("/cost-rates", json=RATES | {"call_minute": "0.15"})

    [last, first] = laura.get("/audit-events", params={"category": "settings"}).json()["items"][:2]
    assert last["action"] == "COST_RATES_UPDATED"
    assert last["details"]["cambios"] == {
        "Minuto de llamada": {"antes": "0.1200", "despues": "0.1500"}
    }


def test_rates_are_validated(laura: TestClient) -> None:
    assert laura.put("/cost-rates", json=RATES | {"call_minute": "-1"}).status_code == 422
    assert laura.put("/cost-rates", json=RATES | {"call_minute": "5000"}).status_code == 422
    assert laura.put("/cost-rates", json=RATES | {"currency": "U$"}).status_code == 422


def test_the_supervisor_sees_costs_but_only_the_admin_changes_rates(
    app: FastAPI, laura: TestClient, database: Database, fibrasur: CompanyWithAdmin
) -> None:
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)
    make_user(database, fibrasur, "pablo@fibrasur.com", UserRole.OPERATOR)
    martin = logged_client(app, "martin@fibrasur.com")
    pablo = logged_client(app, "pablo@fibrasur.com")

    assert martin.get("/costs").status_code == 200
    assert martin.put("/cost-rates", json=RATES).status_code == 403
    assert pablo.get("/costs").status_code == 403
