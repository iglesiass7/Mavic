"""Webhook de fin de llamada. El payload es el ejemplo anonimizado que pasó quien arma el agente."""

import json
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from mavic.core.clock import FixedClock
from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app
from mavic.modules.voice.infrastructure.webhook_signature import sign
from tests.conftest import AGENT_TOKEN, WEBHOOK_SECRET
from tests.factories import invoice_row, logged_client, make_company, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

CALL = "conv_anon_a1b2c3d4"


def payload(conversation_id: str = CALL, event: str = "post_call_transcription") -> dict[str, Any]:
    return {
        "type": event,
        "event_timestamp": 1792173000,
        "data": {
            "agent_id": "agent_anon_debt_001",
            "conversation_id": conversation_id,
            "status": "done",
            "transcript": [
                {
                    "role": "agent",
                    "message": "Hola. Para continuar, necesito validar algunos datos de identidad.",
                    "tool_calls": None,
                    "time_in_call_secs": 0,
                },
                {"role": "user", "message": "Sí, puedo confirmarlos.", "time_in_call_secs": 5},
            ],
            "metadata": {
                "start_time_unix_secs": 1792172940,
                "call_duration_secs": 42,
                "termination_reason": "agent_ended_call",
            },
            "analysis": {
                "evaluation_criteria_results": {"identity_verified": "success"},
                "data_collection_results": {"payment_agreement_type": "no_acuerdo"},
                "call_successful": "success",
                "transcript_summary": "Se realizó la validación inicial.",
            },
        },
    }


def send(
    client: TestClient,
    body: dict[str, Any] | bytes,
    clock: FixedClock,
    *,
    secret: str = WEBHOOK_SECRET,
    age: timedelta = timedelta(0),
) -> Response:
    """Lo que hace ElevenLabs: firma el cuerpo exacto y lo manda."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    timestamp = int((clock.now() - age).timestamp())
    return client.post(
        "/webhooks/elevenlabs",
        content=raw,
        headers={
            "ElevenLabs-Signature": sign(secret, timestamp, raw),
            "Content-Type": "application/json",
        },
    )


@pytest.fixture
def case_with_call(app: FastAPI, database: Database) -> dict[str, Any]:
    """Un caso cuya llamada ya usó una herramienta (así Mavic sabe de qué caso es)."""
    make_company(database, "FibraSur", admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")
    upload(laura, [invoice_row()])
    laura.post("/cases/generate")
    case: dict[str, Any] = laura.get("/cases").json()["items"][0]
    agent = TestClient(app)
    agent.headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
    agent.post(
        "/agent/tools/obtener_contexto_del_caso_v2",
        json={"caso_id": str(case["number"]), "conversation_id": CALL},
    )
    return {"case": case, "laura": laura}


def test_the_transcript_is_stored_on_the_call(
    client: TestClient, clock: FixedClock, case_with_call: dict[str, Any]
) -> None:
    response = send(client, payload(), clock)

    assert response.status_code == 200
    assert response.json() == {"stored": True, "reason": None}
    laura, case = case_with_call["laura"], case_with_call["case"]
    [call] = laura.get(f"/cases/{case['id']}/conversations").json()
    assert call["summary"] == "Se realizó la validación inicial."
    assert call["call_duration_secs"] == 42
    assert call["transcript"][1] == {
        "role": "user",
        "message": "Sí, puedo confirmarlos.",
        "time_in_call_secs": 5,
    }


def test_unknown_calls_and_other_events_are_acknowledged_but_ignored(
    client: TestClient, clock: FixedClock
) -> None:
    unknown = send(client, payload(conversation_id="nunca-uso-herramientas"), clock)
    audio = send(client, payload(event="post_call_audio"), clock)

    # 200 igual: si no, ElevenLabs lo cuenta como falla y termina desactivando el webhook.
    assert unknown.status_code == audio.status_code == 200
    assert unknown.json()["reason"] == "CONVERSACION_DESCONOCIDA"
    assert audio.json()["reason"] == "EVENTO_NO_USADO"


def test_a_forged_signature_is_rejected(client: TestClient, clock: FixedClock) -> None:
    response = send(client, payload(), clock, secret="secreto-equivocado")
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_SIGNATURE"


def test_an_old_message_cannot_be_replayed(client: TestClient, clock: FixedClock) -> None:
    assert send(client, payload(), clock, age=timedelta(minutes=31)).status_code == 401


def test_a_signed_body_that_is_not_json(client: TestClient, clock: FixedClock) -> None:
    response = send(client, b"esto no es json", clock)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_JSON"


def test_webhook_is_off_until_the_secret_is_configured(
    settings: Settings, database: Database, clock: FixedClock
) -> None:
    update = {"elevenlabs_webhook_secret": None}
    app = create_app(settings.model_copy(update=update), database=database, clock=clock)
    response = send(TestClient(app), payload(), clock)
    assert response.status_code == 503
    assert response.json()["code"] == "WEBHOOK_DISABLED"
