"""Auditoría (ADR-036): quién hizo qué, cuándo y sobre qué. Solo se agrega, nunca se borra."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mavic.core.db import Database
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from tests.factories import invoice_row, logged_client, make_company, make_user, rule_body, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    return logged_client(app, "laura@fibrasur.com")


def events(client: TestClient, **params: str) -> list[dict[str, object]]:
    response = client.get("/audit-events", params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, object]] = response.json()["items"]
    return items


def test_each_change_leaves_an_event_with_who_and_what(laura: TestClient) -> None:
    rule = laura.post("/negotiation-rules", json=rule_body(name="Mora alta")).json()
    laura.put(
        f"/negotiation-rules/{rule['id']}", json=rule_body(name="Mora alta", discount_pct="15")
    )
    upload(laura, [invoice_row(external_id="F-1")])
    laura.post("/cases/generate")

    actions = [e["action"] for e in events(laura)]

    # El más nuevo primero. La historia de la empresa empieza cuando se la dio de alta.
    assert actions == [
        "CASES_GENERATED",
        "INVOICES_IMPORTED",
        "RULE_UPDATED",
        "RULE_CREATED",
        "COMPANY_CREATED",
    ]
    [updated] = events(laura, q="Mora alta", category="settings")[:1]
    assert (updated["actor_kind"], updated["actor_name"]) == ("user", "Admin")
    assert updated["level"] == "critical"
    assert updated["details"] == {
        "cambios": {"Descuento (%)": {"antes": "10.00", "despues": "15.00"}}
    }


def test_saving_without_changes_does_not_add_noise(laura: TestClient) -> None:
    rule = laura.post("/negotiation-rules", json=rule_body()).json()
    laura.put(f"/negotiation-rules/{rule['id']}", json=rule_body())

    assert [e["action"] for e in events(laura)] == ["RULE_CREATED", "COMPANY_CREATED"]


def test_filters_by_level_and_day(laura: TestClient) -> None:
    upload(laura, [invoice_row(external_id="F-1")])
    # La hora del evento la pone la base (la hora real de la transacción), no el
    # reloj fijo de los tests: el filtro por día se prueba con el día real.
    today = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    tomorrow = today + timedelta(days=1)

    assert [e["action"] for e in events(laura, level="info")] == ["INVOICES_IMPORTED"]
    assert [e["action"] for e in events(laura, level="critical")] == ["COMPANY_CREATED"]
    assert len(events(laura, since=today.isoformat(), until=today.isoformat())) == 2
    assert events(laura, since=tomorrow.isoformat()) == []


def test_a_company_only_sees_its_own_events(
    app: FastAPI, laura: TestClient, database: Database
) -> None:
    laura.post("/negotiation-rules", json=rule_body())
    make_company(database, "Otra", admin_email="admin@otra.com")
    other = logged_client(app, "admin@otra.com")

    assert [e["action"] for e in events(other)] == ["COMPANY_CREATED"]


def test_the_operator_cannot_read_the_audit(
    app: FastAPI, laura: TestClient, database: Database, fibrasur: CompanyWithAdmin
) -> None:
    make_user(database, fibrasur, "pablo@fibrasur.com", UserRole.OPERATOR)
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)

    assert logged_client(app, "pablo@fibrasur.com").get("/audit-events").status_code == 403
    assert logged_client(app, "martin@fibrasur.com").get("/audit-events").status_code == 200


def test_events_cannot_be_edited_or_deleted_even_from_the_database(
    laura: TestClient, database: Database
) -> None:
    laura.post("/negotiation-rules", json=rule_body())

    with database.session() as session:
        with pytest.raises(DBAPIError, match="solo admite agregar"):
            session.execute(text("UPDATE audit_events SET summary = 'otra cosa'"))
        session.rollback()
        with pytest.raises(DBAPIError, match="solo admite agregar"):
            session.execute(text("DELETE FROM audit_events"))
