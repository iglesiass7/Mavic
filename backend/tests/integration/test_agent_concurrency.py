"""Concurrencia: ElevenLabs manda DOS veces el mismo registro de resultado a la vez.

Pasa en la práctica: si la primera respuesta tarda, el proveedor reintenta.
Sin bloqueo, los dos pedidos ven "todavía no hay resultado" e intentan crear el
acuerdo dos veces: uno de los dos explota con un error de la base (500) y el
agente le dice al deudor que algo falló, aunque el acuerdo SÍ se guardó.

Con `SELECT ... FOR UPDATE` sobre la conversación, el segundo espera al primero,
ve el resultado ya guardado y responde "registrado" sin duplicar nada.

Igual que en el test de reglas, se fuerza el PEOR orden: después de leer la
conversación, cada pedido espera (hasta 1 segundo) a que el otro también la haya leído.
"""

import contextlib
import threading
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mavic.core.clock import FixedClock
from mavic.core.db import Database
from mavic.modules.voice.application import agent_tools
from mavic.modules.voice.domain.outcomes import CallResult, check_registration
from mavic.modules.voice.infrastructure.orm import PaymentAgreementModel
from tests.conftest import AGENT_TOKEN
from tests.factories import invoice_row, logged_client, make_company, rule_body, upload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

CALL = "conv-concurrente"
CLOCK = FixedClock(datetime(2026, 10, 16, 15, 0, tzinfo=UTC), "America/Argentina/Buenos_Aires")


def test_two_identical_registrations_at_the_same_time_create_one_agreement(
    app: FastAPI, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Preparación: un caso con la identidad verificada y el pago único ya ofrecido.
    make_company(database, "FibraSur", admin_email="laura@fibrasur.com")
    laura = logged_client(app, "laura@fibrasur.com")
    laura.post("/negotiation-rules", json=rule_body())
    upload(laura, [invoice_row()])
    laura.post("/cases/generate")
    number = str(laura.get("/cases").json()["items"][0]["number"])
    agent = TestClient(app)
    agent.headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
    ids = {"caso_id": number, "conversation_id": CALL}
    agent.post(
        "/agent/tools/obtener_contexto_del_caso_v2",
        json={**ids, "nombre_consultado": "Ana Torres", "respuesta": "si"},
    )
    agent.post("/agent/tools/obtener_oferta_pago_unico_v2", json=ids)

    # Forzar el peor orden posible.
    both_read = threading.Barrier(2, timeout=1)

    def check_and_wait(*args: Any, **kwargs: Any) -> Any:
        with contextlib.suppress(threading.BrokenBarrierError):
            both_read.wait()
        return check_registration(*args, **kwargs)

    monkeypatch.setattr(
        "mavic.modules.voice.application.agent_tools.check_registration", check_and_wait
    )

    start = threading.Barrier(2)
    answers: list[bool] = []
    errors: list[Exception] = []

    def register() -> None:
        with database.session() as session:
            start.wait()
            try:
                answer = agent_tools.register_result(
                    session,
                    clock=CLOCK,
                    case_reference=number,
                    provider_conversation_id=CALL,
                    result=CallResult.ACUERDO,
                    offer_id="PAGO-UNICO",
                    final_confirmation=True,
                    unknown_count=0,
                )
                answers.append(answer.registered)
            except Exception as error:  # noqa: BLE001 - queremos ver cualquier falla
                errors.append(error)

    threads = [threading.Thread(target=register) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert answers == [True, True]  # el reintento también recibe "registrado"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PaymentAgreementModel)) == 1
