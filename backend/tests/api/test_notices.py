"""Avisos por email y WhatsApp (ADR-038), con remitentes falsos que anotan lo que "mandan".

Escenario (reloj de los tests: viernes 16/10/2026, 12:00 en Argentina):

    FS-1 vence 18/10  (Ana)     ┐ preventivo con 5 días: vencen de 17/10 a 21/10
    FS-2 vence 21/10  (Jorge)   ┘
    FS-3 vence 30/10  (Ana)       fuera de la ventana
    FS-4 vence 16/10  (Lucía)     día de vencimiento
    FS-5 vence 10/09  (Jorge)     vencida: es para el agente, no para los avisos
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from mavic.core.clock import FixedClock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.notices.application.sending import run_scheduled
from mavic.modules.notices.domain.notices import Channel
from mavic.modules.notices.domain.senders import DeliveryError, OutgoingMessage
from mavic.modules.notices.infrastructure.repositories import DeliveryRepository
from tests.factories import invoice_row, logged_client, make_company, make_user, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


class FakeSender:
    def __init__(self, box: "FakeSenders", channel: Channel) -> None:
        self._box, self._channel = box, channel

    def send(self, message: OutgoingMessage) -> str:
        if message.to in self._box.reject:
            raise DeliveryError("El servidor rechazó la dirección del deudor.")
        self._box.sent.append((self._channel, message))
        return f"id-{len(self._box.sent)}"

    def close(self) -> None:
        self._box.closed += 1


class FakeSenders:
    def __init__(self, *, email: bool = True, whatsapp: bool = True) -> None:
        self.ready = {Channel.EMAIL: email, Channel.WHATSAPP: whatsapp}
        self.sent: list[tuple[Channel, OutgoingMessage]] = []
        self.reject: set[str] = set()
        self.closed = 0

    def configured(self, channel: Channel) -> bool:
        return self.ready[channel]

    def sender_for(self, channel: Channel) -> FakeSender | None:
        return FakeSender(self, channel) if self.ready[channel] else None


@pytest.fixture
def senders() -> FakeSenders:
    return FakeSenders()


@pytest.fixture
def app(settings: Settings, database: Database, clock: FixedClock, senders: FakeSenders) -> FastAPI:
    return create_app(settings, database=database, clock=clock, notice_senders=senders)


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    client = logged_client(app, "laura@fibrasur.com")
    ana = {
        "debtor_name": "Ana Torres",
        "debtor_document": "27987654",
        "debtor_email": "ana@example.com",
    }
    jorge = {
        "debtor_name": "Jorge Gómez",
        "debtor_document": "23456789",
        "debtor_email": "jorge@example.com",
        "debtor_phone": "+5491155550103",
    }
    lucia = {
        "debtor_name": "Lucía Fernández",
        "debtor_document": "30555666",
        "debtor_email": "lucia@example.com",
        "debtor_phone": "+5491155550104",
    }
    rows = [
        invoice_row(external_id="FS-1", amount="18500", due_date="2026-10-18", **ana),
        invoice_row(external_id="FS-2", amount="19900", due_date="2026-10-21", **jorge),
        invoice_row(external_id="FS-3", amount="20000", due_date="2026-10-30", **ana),
        invoice_row(external_id="FS-4", amount="15800", due_date="2026-10-16", **lucia),
        invoice_row(external_id="FS-5", amount="9000", due_date="2026-09-10", **jorge),
    ]
    assert upload(client, rows).status_code == 201
    return client


def stage_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "enabled": True,
        "channel": "email",
        "send_time": "09:00",
        "days_before": 5,
        "email_subject": "Tu factura {numero_factura} vence el {vencimiento}",
        "message": "Hola {nombre}: tu factura {numero_factura} por {monto} vence el {vencimiento}.",
        "instructions": "",
        "whatsapp_template_sid": None,
    }
    body.update(overrides)
    return body


def configure(client: TestClient, stage: str, **overrides: Any) -> None:
    response = client.put(f"/notice-settings/{stage}", json=stage_body(**overrides))
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------- configuración


def test_out_of_the_box_both_stages_exist_but_send_nothing_by_themselves(laura: TestClient) -> None:
    body = laura.get("/notice-settings").json()

    stages = {s["stage"]: s for s in body["stages"]}
    assert stages["preventive"]["enabled"] is False
    assert stages["preventive"]["channel"] == "email"
    assert stages["due_today"]["channel"] == "whatsapp"
    assert body["channels_ready"] == {"email": True, "whatsapp": True}
    assert {p["name"] for p in body["placeholders"]} >= {"nombre", "monto", "vencimiento"}


def test_a_typo_in_a_placeholder_is_rejected_before_saving(laura: TestClient) -> None:
    response = laura.put(
        "/notice-settings/preventive", json=stage_body(message="Hola {nombr}, debés {monto}")
    )

    assert response.status_code == 422
    assert response.json()["code"] == "NOTICE_UNKNOWN_PLACEHOLDER"
    assert "{nombr}" in response.json()["detail"]


def test_saving_the_settings_leaves_a_trace_in_the_audit(laura: TestClient) -> None:
    configure(laura, "preventive", days_before=3)

    events = laura.get("/audit-events", params={"category": "settings"}).json()["items"]
    assert events[0]["action"] == "REMINDER_SETTINGS_UPDATED"
    assert events[0]["details"]["cambios"]["Días antes"] == {"antes": 5, "despues": 3}


def test_only_who_manages_rules_changes_the_settings(
    app: FastAPI, laura: TestClient, database: Database, fibrasur: CompanyWithAdmin
) -> None:
    make_user(database, fibrasur, "pablo@fibrasur.com", UserRole.OPERATOR)
    pablo = logged_client(app, "pablo@fibrasur.com")

    assert pablo.get("/notice-settings").status_code == 200
    assert pablo.put("/notice-settings/preventive", json=stage_body()).status_code == 403


# ---------------------------------------------------------------- vista previa y botón


def test_the_preview_counts_who_would_get_the_preventive_notice(laura: TestClient) -> None:
    configure(laura, "preventive")

    preview = laura.get("/notices/preview", params={"stage": "preventive"}).json()

    assert preview["first_due"] == "2026-10-17"
    assert preview["last_due"] == "2026-10-21"
    assert preview["to_send"] == 2  # FS-1 y FS-2
    assert preview["already_sent"] == 0
    assert preview["sample_subject"] == "Tu factura FS-1 vence el 18/10/2026"
    assert (
        preview["sample_body"]
        == "Hola Ana Torres: tu factura FS-1 por $ 18.500,00 vence el 18/10/2026."
    )


def test_the_button_sends_each_notice_once(laura: TestClient, senders: FakeSenders) -> None:
    configure(laura, "preventive")

    first = laura.post("/notices/send", json={"stage": "preventive"}).json()
    second = laura.post("/notices/send", json={"stage": "preventive"}).json()

    assert first["sent"] == 2 and first["failed"] == 0
    assert second["sent"] == 0 and second["already_sent"] == 2
    assert [m.to for _, m in senders.sent] == ["ana@example.com", "jorge@example.com"]
    assert senders.closed == 1  # la conexión se cerró al terminar (la segunda no abrió ninguna)


def test_the_invoices_list_can_show_the_last_notice(laura: TestClient) -> None:
    configure(laura, "preventive")
    laura.post("/notices/send", json={"stage": "preventive"})
    invoices = laura.get("/invoices", params={"stage": "upcoming"}).json()["items"]
    ids = {i["external_id"]: i["id"] for i in invoices}

    notices = laura.get("/notices", params={"invoice_id": [ids["FS-1"], ids["FS-3"]]}).json()

    assert [(n["invoice_id"], n["stage"], n["status"]) for n in notices] == [
        (ids["FS-1"], "preventive", "SENT")
    ]


def test_a_rejected_address_is_recorded_and_can_be_retried(
    laura: TestClient, senders: FakeSenders
) -> None:
    configure(laura, "preventive")
    senders.reject.add("jorge@example.com")

    report = laura.post("/notices/send", json={"stage": "preventive"}).json()
    assert report["sent"] == 1 and report["failed"] == 1
    assert "FS-2" in report["errors"][0]

    senders.reject.clear()
    retry = laura.post("/notices/send", json={"stage": "preventive"}).json()
    assert retry["sent"] == 1  # solo Jorge: a Ana ya le llegó


def test_due_today_goes_by_whatsapp_with_the_payment_instructions(
    laura: TestClient, senders: FakeSenders
) -> None:
    configure(
        laura,
        "due_today",
        channel="whatsapp",
        message="Hola {nombre}, tu factura {numero_factura} vence hoy. {instrucciones}",
        instructions="Pagá en fibrasur.com/pagar",
    )

    report = laura.post("/notices/send", json={"stage": "due_today"}).json()

    assert report["sent"] == 1
    [(channel, message)] = senders.sent
    assert channel is Channel.WHATSAPP
    assert message.to == "+5491155550104"
    assert (
        message.body
        == "Hola Lucía Fernández, tu factura FS-4 vence hoy. Pagá en fibrasur.com/pagar"
    )


def test_an_approved_whatsapp_template_sends_numbered_variables(
    laura: TestClient, senders: FakeSenders
) -> None:
    configure(laura, "due_today", channel="whatsapp", whatsapp_template_sid="HX" + "a" * 32)

    laura.post("/notices/send", json={"stage": "due_today"})

    [(_, message)] = senders.sent
    assert message.template_sid == "HX" + "a" * 32
    assert message.template_variables == {
        "1": "Lucía Fernández",
        "2": "FS-4",
        "3": "$ 15.800,00",
        "4": "16/10/2026",
        "5": "FibraSur",
    }


def test_a_channel_without_credentials_says_what_is_missing(
    settings: Settings, database: Database, clock: FixedClock, fibrasur: CompanyWithAdmin
) -> None:
    app = create_app(
        settings, database=database, clock=clock, notice_senders=FakeSenders(whatsapp=False)
    )
    laura = logged_client(app, "laura@fibrasur.com")
    upload(laura, [invoice_row(external_id="FS-4", due_date="2026-10-16")])

    response = laura.post("/notices/send", json={"stage": "due_today"})

    assert response.status_code == 503
    assert response.json()["code"] == "NOTICE_CHANNEL_NOT_CONFIGURED"
    assert "TWILIO_ACCOUNT_SID" in response.json()["detail"]


def test_the_supervisor_cannot_press_the_button(
    app: FastAPI, laura: TestClient, database: Database, fibrasur: CompanyWithAdmin
) -> None:
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)
    martin = logged_client(app, "martin@fibrasur.com")

    assert martin.get("/notices/preview", params={"stage": "preventive"}).status_code == 200
    assert martin.post("/notices/send", json={"stage": "preventive"}).status_code == 403


def test_another_company_never_sees_these_notices(
    app: FastAPI, laura: TestClient, database: Database
) -> None:
    configure(laura, "preventive")
    laura.post("/notices/send", json={"stage": "preventive"})
    invoice = laura.get("/invoices", params={"stage": "upcoming"}).json()["items"][0]
    make_company(database, "Otra", admin_email="admin@otra.com")
    other = logged_client(app, "admin@otra.com")

    assert other.get("/notices", params={"invoice_id": [invoice["id"]]}).json() == []


# ---------------------------------------------------------------- envío automático


def test_the_worker_sends_once_a_day_after_the_configured_time(
    laura: TestClient, database: Database, clock: FixedClock, senders: FakeSenders
) -> None:
    configure(laura, "preventive", send_time="13:00")  # el reloj está a las 12:00

    assert run_scheduled(database, clock=clock, senders=senders) == []  # todavía no es la hora

    clock.advance(timedelta(hours=1, minutes=5))  # 13:05
    [report] = run_scheduled(database, clock=clock, senders=senders)
    assert report.sent == 2
    assert run_scheduled(database, clock=clock, senders=senders) == []  # hoy ya corrió

    events = laura.get("/audit-events", params={"category": "reminders"}).json()["items"]
    assert events[0]["actor_kind"] == "system"
    assert "automático" in events[0]["summary"]


def test_a_disabled_stage_is_never_sent_automatically(
    laura: TestClient, database: Database, clock: FixedClock, senders: FakeSenders
) -> None:
    configure(laura, "preventive", enabled=False, send_time="00:00")

    assert run_scheduled(database, clock=clock, senders=senders) == []
    assert senders.sent == []


def test_the_worker_records_when_a_channel_is_not_configured(
    laura: TestClient, database: Database, clock: FixedClock
) -> None:
    configure(laura, "due_today", channel="whatsapp", send_time="00:00")

    reports = run_scheduled(database, clock=clock, senders=FakeSenders(whatsapp=False))

    assert reports == []
    [event] = laura.get("/audit-events", params={"category": "reminders"}).json()["items"]
    assert event["action"] == "REMINDERS_NOT_SENT"


def test_a_notice_left_halfway_is_released_and_retried(
    laura: TestClient, database: Database, clock: FixedClock, senders: FakeSenders
) -> None:
    configure(laura, "preventive")
    invoice = laura.get("/invoices", params={"stage": "upcoming"}).json()["items"][0]
    # Un proceso anterior se cortó a mitad de camino, hace una hora.
    with database.session() as session:
        session.execute(
            text(
                "INSERT INTO notice_deliveries (id, company_id, invoice_id, stage, channel, "
                "recipient, status, trigger, content, created_at) SELECT gen_random_uuid(), "
                "company_id, id, 'preventive', 'email', 'x', 'SENDING', 'AUTOMATIC', '{}', :at "
                "FROM invoices WHERE id = :id"
            ),
            {"at": datetime(2026, 10, 16, 14, 0, tzinfo=UTC), "id": invoice["id"]},
        )
        session.commit()

    report = laura.post("/notices/send", json={"stage": "preventive"}).json()

    assert report["sent"] == 2  # el colgado se dio por fallido y se volvió a mandar


def test_two_batches_at_the_same_time_cannot_send_the_same_notice(
    laura: TestClient, database: Database, clock: FixedClock, fibrasur: CompanyWithAdmin
) -> None:
    """El botón y el worker a la vez: el segundo "mandando" choca con el índice único."""
    invoice = laura.get("/invoices", params={"stage": "upcoming"}).json()["items"][0]

    def claim(session: Session) -> uuid.UUID | None:
        return DeliveryRepository(session).claim(
            company_id=fibrasur.company.id,
            invoice_id=uuid.UUID(invoice["id"]),
            stage="preventive",
            channel="email",
            recipient="ana@example.com",
            trigger="MANUAL",
            requested_by=None,
            content={},
            now=clock.now(),
        )

    with database.session() as first, database.session() as second:
        assert claim(first) is not None
        first.commit()
        assert claim(second) is None  # no manda
