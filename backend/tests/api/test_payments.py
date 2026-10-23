"""Seguimiento de pagos (ADR-037): cuotas con fecha, registro manual y estado.

Escenario (reloj de los tests: 16/10/2026):
    FibraSur, regla "Corto plazo": 5 días para pagar, 10 % de descuento o 6 cuotas al 12 %.
    Ana Torres (caso con 120.000,50) acepta CUOTAS-6-CON-INTERES por teléfono.
    -> 6 cuotas de 22.400,09: la primera el 21/10/2026 y después cada mes.
"""

from datetime import timedelta
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
from tests.api.test_outbound_calls import FakeGateway, call_settings, case_of, webhook
from tests.factories import invoice_row, logged_client, make_company, make_user, rule_body, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


@pytest.fixture
def app(settings: Settings, database: Database, clock: FixedClock) -> FastAPI:
    return create_app(
        call_settings(settings), database=database, clock=clock, call_gateway=FakeGateway()
    )


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    client = logged_client(app, "laura@fibrasur.com")
    client.post(
        "/negotiation-rules",
        json=rule_body(max_installments=6, interest_pct="12", discount_pct="10"),
    )
    ana = {"debtor_name": "Ana Torres", "debtor_document": "27987654"}
    rows = [
        invoice_row(external_id="FAC-1001", amount="70000", **ana),
        invoice_row(external_id="FAC-1002", amount="50000.50", **ana),
    ]
    assert upload(client, rows).status_code == 201
    client.post("/cases/generate")
    return client


def agree(laura: TestClient, clock: FixedClock, offer_id: str) -> dict[str, Any]:
    """Llama a Ana y el webhook trae un ACUERDO con esa oferta. Devuelve el acuerdo."""
    case = case_of(laura, "Ana Torres")
    started = laura.post(f"/cases/{case['id']}/calls").json()
    response = webhook(
        laura,
        clock,
        conversation_id=started["provider_conversation_id"],
        resultado="ACUERDO",
        oferta_id=offer_id,
    )
    assert response.status_code == 200, response.text
    [agreement] = laura.get(f"/cases/{case['id']}/agreements").json()
    result: dict[str, Any] = agreement
    return result


def pay(client: TestClient, agreement: dict[str, Any], number: int, **body: Any) -> dict[str, Any]:
    response = client.post(
        f"/agreements/{agreement['id']}/installments/{number}/payment", json=body
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# ---------------------------------------------------------------- cuotas


def test_an_installment_agreement_gets_dated_installments(
    laura: TestClient, clock: FixedClock
) -> None:
    agreement = agree(laura, clock, "CUOTAS-6-CON-INTERES")

    assert agreement["status"] == "active"
    assert agreement["installment_count"] == 6
    dates = [i["due_date"] for i in agreement["installments"]]
    assert dates == [
        "2026-10-21",  # 16/10 + 5 días de la regla
        "2026-11-21",
        "2026-12-21",
        "2027-01-21",
        "2027-02-21",
        "2027-03-21",
    ]
    amounts = {i["amount"] for i in agreement["installments"]}
    assert amounts == {agreement["installment_amount"]}  # cuotas iguales (ADR-034)
    assert agreement["paid_amount"] == "0"
    assert agreement["pending_amount"] == agreement["total_amount"]
    assert agreement["next_due_date"] == "2026-10-21"


def test_a_single_payment_is_one_installment(laura: TestClient, clock: FixedClock) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")

    [only] = agreement["installments"]
    assert only["due_date"] == "2026-10-21"
    assert only["amount"] == agreement["total_amount"]


def test_paying_everything_fulfills_the_agreement_and_closes_the_case(
    laura: TestClient, clock: FixedClock
) -> None:
    agreement = agree(laura, clock, "CUOTAS-6-CON-INTERES")

    for number in range(1, 6):
        result = pay(laura, agreement, number, note="transferencia")
        assert result["status"] == "active"
    assert case_of(laura, "Ana Torres")["status"] == "agreement"

    result = pay(laura, agreement, 6)

    assert result["status"] == "fulfilled"
    assert result["pending_amount"] == "0"
    assert result["paid_amount"] == result["total_amount"]
    assert result["next_due_date"] is None
    assert case_of(laura, "Ana Torres")["status"] == "closed"


def test_undoing_a_payment_reopens_the_closed_case(laura: TestClient, clock: FixedClock) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")
    pay(laura, agreement, 1)
    assert case_of(laura, "Ana Torres")["status"] == "closed"

    response = laura.post(
        f"/agreements/{agreement['id']}/installments/1/undo-payment",
        json={"reason": "Se cargó en el caso equivocado"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert response.json()["installments"][0]["paid_on"] is None
    assert case_of(laura, "Ana Torres")["status"] == "agreement"


def test_an_unpaid_installment_after_its_date_makes_the_agreement_late(
    app: FastAPI, laura: TestClient, clock: FixedClock
) -> None:
    agreement = agree(laura, clock, "CUOTAS-6-CON-INTERES")
    case_id = agreement["case_id"]

    clock.advance(timedelta(days=5))  # 21/10: vence hoy, todavía está a tiempo
    laura = logged_client(app, "laura@fibrasur.com")  # la sesión anterior ya venció
    assert laura.get(f"/cases/{case_id}/agreements").json()[0]["status"] == "active"

    clock.advance(timedelta(days=1))  # 22/10: venció sin pago
    laura = logged_client(app, "laura@fibrasur.com")
    [late] = laura.get(f"/cases/{case_id}/agreements").json()
    assert late["status"] == "late"
    assert late["installments"][0]["overdue"] is True
    assert late["installments"][1]["overdue"] is False

    # Pagó tarde: vuelve a estar al día.
    paid = pay(laura, agreement, 1, paid_on="2026-10-22")
    assert paid["status"] == "active"


# ---------------------------------------------------------------- validaciones


@pytest.mark.parametrize(
    ("paid_on", "code"),
    [
        ("2026-10-17", "PAYMENT_DATE_IN_FUTURE"),  # el reloj está en 16/10
        ("2026-10-15", "PAYMENT_BEFORE_AGREEMENT"),
    ],
)
def test_payment_dates_must_make_sense(
    laura: TestClient, clock: FixedClock, paid_on: str, code: str
) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")

    response = laura.post(
        f"/agreements/{agreement['id']}/installments/1/payment", json={"paid_on": paid_on}
    )

    assert response.status_code == 422
    assert response.json()["code"] == code


def test_a_payment_cannot_be_recorded_twice(laura: TestClient, clock: FixedClock) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")
    pay(laura, agreement, 1)

    response = laura.post(f"/agreements/{agreement['id']}/installments/1/payment", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "INSTALLMENT_ALREADY_PAID"


def test_undo_needs_a_reason(laura: TestClient, clock: FixedClock) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")
    pay(laura, agreement, 1)

    response = laura.post(
        f"/agreements/{agreement['id']}/installments/1/undo-payment", json={"reason": "   "}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UNDO_REASON_REQUIRED"


def test_supervisor_sees_but_cannot_record_payments(
    app: FastAPI,
    laura: TestClient,
    clock: FixedClock,
    database: Database,
    fibrasur: CompanyWithAdmin,
) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)
    martin = logged_client(app, "martin@fibrasur.com")

    assert martin.get(f"/cases/{agreement['case_id']}/agreements").status_code == 200
    response = martin.post(f"/agreements/{agreement['id']}/installments/1/payment", json={})
    assert response.status_code == 403


def test_another_company_cannot_touch_the_agreement(
    app: FastAPI, laura: TestClient, clock: FixedClock, database: Database
) -> None:
    agreement = agree(laura, clock, "PAGO-UNICO")
    make_company(database, "Otra", admin_email="admin@otra.com")
    other = logged_client(app, "admin@otra.com")

    response = other.post(f"/agreements/{agreement['id']}/installments/1/payment", json={})

    assert response.status_code == 404
    assert other.get(f"/cases/{agreement['case_id']}/agreements").json() == []


# ---------------------------------------------------------------- tablero


def test_the_dashboard_counts_payments(laura: TestClient, clock: FixedClock) -> None:
    agreement = agree(laura, clock, "CUOTAS-6-CON-INTERES")
    pay(laura, agreement, 1)
    each = agreement["installment_amount"]

    payments = laura.get("/dashboard").json()["payments"]

    assert payments == {
        "active": 1,
        "fulfilled": 0,
        "late": 0,
        "collected_amount": each,
        "pending_amount": str(round(5 * float(each), 2)),
        "overdue_amount": "0",
    }
