"""Botón "Llamar" y webhook del agente nuevo (ADR-034), de punta a punta.

ElevenLabs se reemplaza por `FakeGateway`: no se llama a nadie, pero se
comprueba exactamente qué se le habría mandado.

Escenario (reloj de los tests: 16/10/2026):
    FibraSur, regla "Corto plazo" (15 a 59 días, 10 % de descuento, 6 cuotas al 12 %)
    Ana Torres   2 facturas: 70.000 + 50.000,50  vencidas el 10/09 (36 días) -> caso con oferta
    Bruno Paz    1 factura de 5.000 vencida el 10/10 (6 días)              -> caso sin regla
"""

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from mavic.core.clock import FixedClock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.voice.application import webhooks
from mavic.modules.voice.domain.call_gateway import CallGatewayError, OutboundCallResult
from mavic.modules.voice.infrastructure.orm import WebhookEventModel
from mavic.modules.voice.infrastructure.webhook_signature import sign
from tests.conftest import WEBHOOK_SECRET
from tests.factories import invoice_row, logged_client, make_company, make_user, rule_body, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

AGENT_ID = "agent_prueba_gestion_de_deuda"
BRANCH_ID = "rama_prueba_nuevo_mavic"


class FakeGateway:
    """Hace de ElevenLabs. `on_call` permite simular algo DURANTE el pedido."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None
        self.result: OutboundCallResult | None = None
        self.on_call: Callable[[dict[str, Any]], object] | None = None

    def start_call(
        self, *, to_number: str, dynamic_variables: dict[str, Any], branch_id: str | None
    ) -> OutboundCallResult:
        call = {"to": to_number, "variables": dynamic_variables, "branch_id": branch_id}
        self.calls.append(call)
        if self.on_call:
            self.on_call(call)
        if self.error:
            raise self.error
        n = len(self.calls)
        return self.result or OutboundCallResult(
            accepted=True, message="ok", conversation_id=f"conv_{n}", call_sid=f"CA{n:032d}"
        )


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


def call_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"elevenlabs_agent_id": AGENT_ID, "elevenlabs_branch_id": BRANCH_ID}
    )


@pytest.fixture
def app(settings: Settings, database: Database, clock: FixedClock, gateway: FakeGateway) -> FastAPI:
    return create_app(call_settings(settings), database=database, clock=clock, call_gateway=gateway)


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
    bruno = {
        "debtor_name": "Bruno Paz",
        "debtor_document": "20111222",
        "debtor_phone": "+5491155550103",
        "debtor_email": "bruno@example.com",
    }
    rows = [
        invoice_row(
            external_id="FAC-1001", description="Factura de servicio vencida", amount="70000", **ana
        ),
        invoice_row(
            external_id="FAC-1002",
            description="Saldo de financiación vencido",
            amount="50000.50",
            **ana,
        ),
        invoice_row(external_id="FAC-2001", amount="5000", due_date="2026-10-10", **bruno),
    ]
    assert upload(client, rows).status_code == 201
    assert client.post("/cases/generate").json()["cases_created"] == 2
    return client


def case_of(laura: TestClient, name: str) -> dict[str, Any]:
    items = laura.get("/cases").json()["items"]
    return next(item for item in items if item["debtor"]["name"] == name)


def calls_of(laura: TestClient, case: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = laura.get(f"/cases/{case['id']}/conversations").json()
    return result


def webhook(
    client: TestClient,
    clock: FixedClock,
    *,
    conversation_id: str | None,
    caso_id: str | None = None,
    resultado: str | None = "CONTACTADO",
    oferta_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Response:
    collected: dict[str, Any] = {}
    if resultado is not None:
        collected["resultado"] = {"data_collection_id": "resultado", "value": resultado}
    collected["oferta_id"] = {"data_collection_id": "oferta_id", "value": oferta_id}
    data: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "conversation_id": conversation_id,
        "status": "done",
        "branch_id": BRANCH_ID,
        "version_id": "agtvrsn_prueba",
        "transcript": [
            {"role": "agent", "message": "Hola, ¿hablo con Ana Torres?", "time_in_call_secs": 0},
            {"role": "user", "message": "Sí, soy yo.", "time_in_call_secs": 3},
        ],
        "metadata": {"call_duration_secs": 95, "termination_reason": "end_call tool was called."},
        "analysis": {
            "call_successful": "success",
            "transcript_summary": "Ana atendió.",
            "data_collection_results": collected,
        },
        "conversation_initiation_client_data": {
            "dynamic_variables": {"caso_id": caso_id} if caso_id else {}
        },
    }
    body = {"type": "post_call_transcription", "event_timestamp": 1792173000, "data": data}
    body.update(extra or {})
    raw = json.dumps(body).encode()
    timestamp = int(clock.now().timestamp())
    return client.post(
        "/webhooks/elevenlabs",
        content=raw,
        headers={"ElevenLabs-Signature": sign(WEBHOOK_SECRET, timestamp, raw)},
    )


# ---------------------------------------------------------------- iniciar la llamada


def test_calling_sends_the_exact_contract_and_saves_the_ids(
    laura: TestClient, gateway: FakeGateway
) -> None:
    ana = case_of(laura, "Ana Torres")

    response = laura.post(f"/cases/{ana['id']}/calls")

    assert response.status_code == 201
    assert response.json()["status"] == "INITIATED"
    assert response.json()["provider_conversation_id"] == "conv_1"
    assert response.json()["provider_call_sid"] == "CA" + "1".zfill(32)
    [sent] = gateway.calls
    assert sent["to"] == "+5491155550102"
    assert sent["branch_id"] == BRANCH_ID  # la prueba no cae en la rama por defecto
    variables = sent["variables"]
    assert list(variables) == [
        "caso_id",
        "nombre",
        "nombre_acreedor",
        "cantidad_deudas",
        "monto_total",
        "moneda_total",
        "deudas",
        "ofertas",
    ]
    assert variables["caso_id"] == str(ana["number"])
    assert variables["nombre_acreedor"] == "FibraSur"
    assert variables["cantidad_deudas"] == 2
    assert variables["monto_total"] == 120000.5
    assert [o["oferta_id"] for o in json.loads(variables["ofertas"])] == [
        "PAGO-UNICO",
        "CUOTAS-6-CON-INTERES",
    ]

    [call] = calls_of(laura, ana)
    assert call["origin"] == "OUTBOUND"
    assert call["status"] == "INITIATED"
    assert call["offered"] == ["PAGO-UNICO", "CUOTAS-6-CON-INTERES"]
    assert call["identity_verified"] is None  # el flujo nuevo no verifica en Mavic


def test_the_call_exists_before_elevenlabs_is_asked(
    laura: TestClient, gateway: FakeGateway
) -> None:
    ana = case_of(laura, "Ana Torres")
    seen: list[str] = []
    gateway.on_call = lambda _: seen.extend(c["status"] for c in calls_of(laura, ana))

    laura.post(f"/cases/{ana['id']}/calls")

    assert seen == ["INITIATING"]


def test_a_failed_start_is_recorded_and_does_not_block_the_case(
    laura: TestClient, gateway: FakeGateway
) -> None:
    ana = case_of(laura, "Ana Torres")
    gateway.error = CallGatewayError("HTTP 422: número inválido")

    response = laura.post(f"/cases/{ana['id']}/calls")

    assert response.status_code == 503
    assert response.json()["code"] == "CALL_NOT_STARTED"
    [failed] = calls_of(laura, ana)
    assert failed["status"] == "FAILED"
    assert failed["failure_reason"] == "HTTP 422: número inválido"
    # Se puede volver a intentar enseguida.
    gateway.error = None
    assert laura.post(f"/cases/{ana['id']}/calls").status_code == 201


def test_elevenlabs_saying_no_is_also_a_failure(laura: TestClient, gateway: FakeGateway) -> None:
    ana = case_of(laura, "Ana Torres")
    gateway.result = OutboundCallResult(
        accepted=False, message="Twilio rechazó el número", conversation_id=None, call_sid=None
    )

    assert laura.post(f"/cases/{ana['id']}/calls").status_code == 503
    assert calls_of(laura, ana)[0]["failure_reason"] == "Twilio rechazó el número"


def test_a_second_call_waits_for_the_first_one(
    app: FastAPI,
    laura: TestClient,
    settings: Settings,
    database: Database,
    clock: FixedClock,
    gateway: FakeGateway,
) -> None:
    ana = case_of(laura, "Ana Torres")
    assert laura.post(f"/cases/{ana['id']}/calls").status_code == 201

    again = laura.post(f"/cases/{ana['id']}/calls")
    assert again.status_code == 409
    assert again.json()["code"] == "CALL_IN_PROGRESS"

    # Media hora después sin webhook, se asume perdida y se puede volver a llamar.
    later = FixedClock(clock.now() + timedelta(minutes=31), "America/Argentina/Buenos_Aires")
    app_later = create_app(
        call_settings(settings), database=database, clock=later, call_gateway=gateway
    )
    laura_later = logged_client(app_later, "laura@fibrasur.com")
    assert laura_later.post(f"/cases/{ana['id']}/calls").status_code == 201


def test_a_case_without_a_rule_is_not_called(laura: TestClient, gateway: FakeGateway) -> None:
    bruno = case_of(laura, "Bruno Paz")

    response = laura.post(f"/cases/{bruno['id']}/calls")

    assert response.status_code == 409
    assert response.json()["code"] == "NO_MATCHING_RULE"
    assert gateway.calls == []


def test_only_operators_and_admins_can_call(
    app: FastAPI, laura: TestClient, database: Database, fibrasur: CompanyWithAdmin
) -> None:
    ana = case_of(laura, "Ana Torres")
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)
    martin = logged_client(app, "martin@fibrasur.com")

    assert martin.post(f"/cases/{ana['id']}/calls").status_code == 403


def test_calls_are_off_without_elevenlabs_credentials(
    settings: Settings, database: Database, clock: FixedClock, laura: TestClient
) -> None:
    ana = case_of(laura, "Ana Torres")
    app = create_app(settings, database=database, clock=clock)  # sin credenciales de llamadas
    client = logged_client(app, "laura@fibrasur.com")

    response = client.post(f"/cases/{ana['id']}/calls")

    assert response.status_code == 503
    assert response.json()["code"] == "CALLS_DISABLED"


# ---------------------------------------------------------------- webhook


def test_the_webhook_applies_the_result_and_stores_the_transcript(
    client: TestClient, laura: TestClient, clock: FixedClock
) -> None:
    ana = case_of(laura, "Ana Torres")
    laura.post(f"/cases/{ana['id']}/calls")

    response = webhook(client, clock, conversation_id="conv_1", oferta_id="PAGO-UNICO")

    assert response.json() == {"stored": True, "reason": None}
    assert case_of(laura, "Ana Torres")["status"] == "contacted"
    [call] = calls_of(laura, ana)
    assert call["status"] == "DONE"
    assert call["result"] == "CONTACTADO"
    assert call["agreement"] is None  # un oferta_id suelto sin ACUERDO no significa nada
    assert call["summary"] == "Ana atendió."
    assert call["call_duration_secs"] == 95
    assert call["transcript"][1]["message"] == "Sí, soy yo."


def test_an_agreement_copies_the_numbers_from_the_snapshot(
    client: TestClient, laura: TestClient, clock: FixedClock
) -> None:
    ana = case_of(laura, "Ana Torres")
    laura.post(f"/cases/{ana['id']}/calls")
    # Después de iniciar la llamada, alguien cambia la regla: el acuerdo NO cambia.
    [rule] = laura.get("/negotiation-rules").json()
    changed = laura.put(
        f"/negotiation-rules/{rule['id']}",
        json=rule_body(max_installments=6, interest_pct="50", discount_pct="10", is_active=True),
    )
    assert changed.status_code == 200

    webhook(
        client,
        clock,
        conversation_id="conv_1",
        resultado="ACUERDO",
        oferta_id="CUOTAS-6-CON-INTERES",
    )

    assert case_of(laura, "Ana Torres")["status"] == "agreement"
    agreement = calls_of(laura, ana)[0]["agreement"]
    assert agreement["modality"] == "CUOTAS"
    assert agreement["installment_count"] == 6
    assert agreement["installment_amount"] == "22400.09"  # 120.000,50 + 12 %, en 6 iguales
    assert agreement["total_amount"] == "134400.54"
    assert agreement["original_amount"] == "120000.50"
    assert agreement["schedule"] is None  # el agente no pacta fechas


@pytest.mark.parametrize(
    ("resultado", "oferta_id", "reason"),
    [
        ("ACUERDO", "OF-INVENTADA", "OFERTA_DESCONOCIDA"),
        ("ACUERDO", None, "ACUERDO_SIN_OFERTA"),
        ("TAL VEZ", None, "RESULTADO_INVALIDO"),
        (None, None, "SIN_RESULTADO"),
    ],
)
def test_doubtful_results_go_to_review_and_change_nothing(
    client: TestClient,
    laura: TestClient,
    clock: FixedClock,
    resultado: str | None,
    oferta_id: str | None,
    reason: str,
) -> None:
    ana = case_of(laura, "Ana Torres")
    laura.post(f"/cases/{ana['id']}/calls")

    response = webhook(
        client, clock, conversation_id="conv_1", resultado=resultado, oferta_id=oferta_id
    )

    assert response.status_code == 200
    assert response.json()["reason"] == reason
    assert case_of(laura, "Ana Torres")["status"] == "pending"
    [call] = calls_of(laura, ana)
    assert call["status"] == "NEEDS_REVIEW"
    assert call["review_reason"] == reason
    assert call["agreement"] is None
    assert call["transcript"]  # igual se guarda todo


@pytest.mark.parametrize(
    ("resultado", "status"),
    [("DESCONOCIMIENTO", "disputed"), ("DERIVACION_HUMANA", "escalated")],
)
def test_other_results_change_the_case_and_ignore_the_offer(
    client: TestClient, laura: TestClient, clock: FixedClock, resultado: str, status: str
) -> None:
    ana = case_of(laura, "Ana Torres")
    laura.post(f"/cases/{ana['id']}/calls")

    webhook(client, clock, conversation_id="conv_1", resultado=resultado, oferta_id="PAGO-UNICO")

    assert case_of(laura, "Ana Torres")["status"] == status
    assert calls_of(laura, ana)[0]["agreement"] is None


def test_a_repeated_webhook_does_not_duplicate_anything(
    client: TestClient, laura: TestClient, clock: FixedClock
) -> None:
    ana = case_of(laura, "Ana Torres")
    laura.post(f"/cases/{ana['id']}/calls")

    def send(extra: dict[str, Any] | None = None) -> Response:
        return webhook(
            client,
            clock,
            conversation_id="conv_1",
            resultado="ACUERDO",
            oferta_id="PAGO-UNICO",
            extra=extra,
        )

    first = send()
    same_body = send()
    other_body = send({"event_timestamp": 1792173999})  # reenvío con otro cuerpo

    assert first.json() == {"stored": True, "reason": None}
    assert same_body.json()["reason"] == other_body.json()["reason"] == "YA_PROCESADO"
    [call] = calls_of(laura, ana)
    assert call["agreement"]["total_amount"] == "108000.45"
    dashboard = laura.get("/dashboard").json()["agent"]
    assert dashboard["agreements"] == 1


def test_a_webhook_that_arrives_before_the_ids_are_saved_is_matched_by_case(
    app: FastAPI, laura: TestClient, clock: FixedClock, gateway: FakeGateway
) -> None:
    """ElevenLabs puede mandar el webhook antes de que Mavic guarde el conversation_id."""
    ana = case_of(laura, "Ana Torres")
    other_client = TestClient(app)
    gateway.on_call = lambda call: webhook(
        other_client,
        clock,
        conversation_id="conv_1",
        caso_id=call["variables"]["caso_id"],
        resultado="CONTACTADO",
    )

    response = laura.post(f"/cases/{ana['id']}/calls")

    assert response.json()["status"] == "DONE"  # el webhook ya la había cerrado
    [call] = calls_of(laura, ana)
    assert call["provider_conversation_id"] == "conv_1"
    assert call["result"] == "CONTACTADO"
    assert case_of(laura, "Ana Torres")["status"] == "contacted"


def test_a_call_that_never_used_tools_is_not_lost(
    client: TestClient, laura: TestClient, clock: FixedClock
) -> None:
    """Regresión central: una llamada sin herramientas (por ejemplo, una prueba
    desde la consola de ElevenLabs) se encuentra por el caso_id de sus variables."""
    ana = case_of(laura, "Ana Torres")

    response = webhook(
        client,
        clock,
        conversation_id="conv_consola",
        caso_id=str(ana["number"]),
        resultado="CONTACTADO",
    )

    assert response.json() == {"stored": True, "reason": None}
    [call] = calls_of(laura, ana)
    assert call["origin"] == "EXTERNAL"
    assert call["transcript"]
    assert case_of(laura, "Ana Torres")["status"] == "contacted"


def test_an_agreement_from_outside_mavic_goes_to_review(
    client: TestClient, laura: TestClient, clock: FixedClock
) -> None:
    """Sin foto de ofertas, un ACUERDO no se puede validar: no se crea solo."""
    ana = case_of(laura, "Ana Torres")

    response = webhook(
        client,
        clock,
        conversation_id="conv_consola",
        caso_id=str(ana["number"]),
        resultado="ACUERDO",
        oferta_id="PAGO-UNICO",
    )

    assert response.json()["reason"] == "ACUERDO_SIN_FOTO"
    assert case_of(laura, "Ana Torres")["status"] == "pending"


def test_two_cases_do_not_mix(client: TestClient, laura: TestClient, clock: FixedClock) -> None:
    ana, bruno = case_of(laura, "Ana Torres"), case_of(laura, "Bruno Paz")
    laura.post(f"/cases/{ana['id']}/calls")

    webhook(
        client,
        clock,
        conversation_id="conv_de_bruno",
        caso_id=str(bruno["number"]),
        resultado="DERIVACION_HUMANA",
    )

    assert case_of(laura, "Bruno Paz")["status"] == "escalated"
    assert case_of(laura, "Ana Torres")["status"] == "pending"
    assert calls_of(laura, ana)[0]["status"] == "INITIATED"  # sigue esperando su webhook


def test_an_unknown_call_is_kept_for_later(
    client: TestClient, clock: FixedClock, database: Database
) -> None:
    response = webhook(client, clock, conversation_id="conv_x", caso_id="999999")

    assert response.json() == {"stored": False, "reason": "CONVERSACION_DESCONOCIDA"}
    with database.session() as session:
        [event] = session.scalars(select(WebhookEventModel)).all()
        assert event.processed_at is None  # guardado, pendiente
        assert event.outcome == "CONVERSACION_DESCONOCIDA"


def test_a_database_failure_answers_500_and_the_retry_works(
    app: FastAPI,
    laura: TestClient,
    clock: FixedClock,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ana = case_of(laura, "Ana Torres")
    laura.post(f"/cases/{ana['id']}/calls")
    original = webhooks._apply_result
    failures = iter([True])

    def flaky(*args: Any, **kwargs: Any) -> str | None:
        if next(failures, False):
            raise OperationalError("UPDATE", {}, Exception("la base se reinició"))
        return original(*args, **kwargs)

    monkeypatch.setattr(webhooks, "_apply_result", flaky)
    elevenlabs = TestClient(app, raise_server_exceptions=False)

    first = webhook(elevenlabs, clock, conversation_id="conv_1")
    retry = webhook(elevenlabs, clock, conversation_id="conv_1")

    assert first.status_code == 500  # ElevenLabs reintenta
    with database.session() as session:
        assert len(session.scalars(select(WebhookEventModel)).all()) == 1  # quedó guardado
    assert retry.json() == {"stored": True, "reason": None}
    assert case_of(laura, "Ana Torres")["status"] == "contacted"


def test_the_dashboard_counts_only_finished_calls(
    client: TestClient, laura: TestClient, clock: FixedClock, gateway: FakeGateway
) -> None:
    ana = case_of(laura, "Ana Torres")
    gateway.error = CallGatewayError("sin señal")
    laura.post(f"/cases/{ana['id']}/calls")  # FAILED: no cuenta
    gateway.error = None
    laura.post(f"/cases/{ana['id']}/calls")  # INITIATED: todavía no cuenta
    assert laura.get("/dashboard").json()["agent"]["calls"] == 0

    webhook(client, clock, conversation_id="conv_2", resultado="CONTACTADO")

    agent = laura.get("/dashboard").json()["agent"]
    assert agent["calls"] == 1
    assert agent["calls_by_result"]["CONTACTADO"] == 1
