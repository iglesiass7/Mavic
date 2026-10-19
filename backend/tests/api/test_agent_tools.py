"""Herramientas del agente de voz: llamadas completas, como las haría ElevenLabs.

Escenario: FibraSur tiene una regla de 15 a 59 días de atraso (10 % de descuento
o 3 cuotas sin interés). Ana Torres debe 120.000 desde el 10/09 (36 días al
16/10, la fecha del reloj de los tests).
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from mavic.core.config import Settings
from mavic.core.db import Database
from mavic.main import create_app
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.portfolio.infrastructure.orm import CaseModel
from tests.conftest import AGENT_TOKEN
from tests.factories import (
    invoice_row,
    logged_client,
    make_company,
    make_user,
    rule_body,
    upload,
)
from tests.unit.test_voice_domain import ELEVENLABS_HISTORY

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

CALL = "conv_anon_a1b2c3d4"


@pytest.fixture
def fibrasur(database: Database) -> CompanyWithAdmin:
    return make_company(database, "FibraSur", admin_email="laura@fibrasur.com")


@pytest.fixture
def laura(app: FastAPI, fibrasur: CompanyWithAdmin) -> TestClient:
    return logged_client(app, "laura@fibrasur.com")


@pytest.fixture
def agent(app: FastAPI) -> TestClient:
    """Lo que hace ElevenLabs: llama con el token en el encabezado Authorization."""
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
    return client


@pytest.fixture
def case(laura: TestClient) -> dict[str, Any]:
    """El caso de Ana, con la regla de corto plazo. Devuelve {id, number}."""
    laura.post("/negotiation-rules", json=rule_body(name="Corto plazo"))
    upload(
        laura, [invoice_row(amount="120000", due_date="2026-09-10", description="Abono internet")]
    )
    laura.post("/cases/generate")
    item: dict[str, Any] = laura.get("/cases").json()["items"][0]
    return item


def tool(agent: TestClient, name: str, **params: Any) -> Any:
    response = agent.post(f"/agent/tools/{name}", json=params)
    assert response.status_code == 200, response.text
    return response.json()


def verify_identity(agent: TestClient, case: dict[str, Any], call: str = CALL) -> Any:
    return tool(
        agent,
        "obtener_contexto_del_caso_v2",
        caso_id=str(case["number"]),
        conversation_id=call,
        nombre_consultado="Ana Torres",
        respuesta="sí",
    )


def ids(case: dict[str, Any], call: str = CALL) -> dict[str, str]:
    return {"caso_id": str(case["number"]), "conversation_id": call}


def case_status(laura: TestClient, case: dict[str, Any]) -> str:
    status: str = laura.get(f"/cases/{case['id']}").json()["status"]
    return status


# ---------------------------------------------------------------- llamada completa


def test_a_whole_call_that_ends_in_an_agreement(
    agent: TestClient, laura: TestClient, case: dict[str, Any]
) -> None:
    context = verify_identity(agent, case)
    assert context == {
        "caso_id": str(case["number"]),
        "nombre": "Ana Torres",
        "identidad_verificada": True,
        "pago_unico_ofrecido": False,
        "cuotas_ofrecidas": False,
        "ofertas_restantes": 2,
        "datos_comunicables": {
            "nombre_acreedor": "FibraSur",
            "contexto_deuda": "Abono internet",
            "monto_original": 120000,  # número JSON, como lo espera el agente
            "moneda": "ARS",
            "fecha_vencimiento_original": "2026-09-10",
        },
    }

    single = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))
    assert single == {
        "has_offer": True,
        "pago_unico_ofrecido": True,
        "ofertas_restantes": 1,
        "oferta_id": "PAGO-UNICO",
        "modalidad": "PAGO_UNICO",
        "moneda": "ARS",
        "importe_original": 120000,
        "descuento_porcentaje": 10,
        "descuento": 12000,
        "importe_total": 108000,
        "fecha_limite_pago": "2026-10-21",
        "motivo": None,
    }

    plan = tool(agent, "obtener_oferta_cuotas_v2", **ids(case))
    assert (plan["oferta_id"], plan["cantidad_cuotas"], plan["importe_por_cuota"]) == (
        "CUOTAS-3-SIN-INTERES",
        3,
        40000,
    )
    assert (plan["cuotas_ofrecidas"], plan["ofertas_restantes"]) == (True, 0)

    result = tool(
        agent,
        "registrar_resultado_v2",
        **ids(case),
        resultado="ACUERDO",
        oferta_id="CUOTAS-3-SIN-INTERES",
        confirmacion_final=True,
        cantidad_desconocimientos=0,
    )
    assert result == {
        "registrado": True,
        "resultado": "ACUERDO",
        "oferta_id": "CUOTAS-3-SIN-INTERES",
        "motivo": None,
    }
    assert case_status(laura, case) == "agreement"

    [call] = laura.get(f"/cases/{case['id']}/conversations").json()
    assert call["identity_verified"] is True
    assert call["offered"] == ["PAGO-UNICO", "CUOTAS-3-SIN-INTERES"]
    agreement = call["agreement"]
    assert (agreement["modality"], agreement["total_amount"]) == ("CUOTAS", "120000.00")
    assert [i["due_date"] for i in agreement["schedule"]] == [
        "2026-10-21",
        "2026-11-21",
        "2026-12-21",
    ]


def test_the_tools_also_work_with_get_and_query_parameters(
    agent: TestClient, case: dict[str, Any]
) -> None:
    params = {**ids(case), "nombre_consultado": "Ana", "respuesta": "si"}
    response = agent.get("/agent/tools/obtener_contexto_del_caso_v2", params=params)
    assert response.json()["identidad_verificada"] is True


def test_the_case_id_can_have_a_prefix(agent: TestClient, case: dict[str, Any]) -> None:
    context = tool(
        agent,
        "obtener_contexto_del_caso_v2",
        caso_id=f"CASO-{case['number']}",
        conversation_id=CALL,
        nombre_consultado="Ana Torres",
        respuesta=True,
    )
    assert context["identidad_verificada"] is True


# ---------------------------------------------------------------- identidad


@pytest.mark.parametrize(
    ("asked", "answer"), [("Ana Torres", "no"), ("Ricardo Pérez", "sí"), ("Ana Torres", "")]
)
def test_without_identity_no_debt_data_and_no_offers(
    agent: TestClient, case: dict[str, Any], asked: str, answer: str
) -> None:
    context = tool(
        agent,
        "obtener_contexto_del_caso_v2",
        **ids(case),
        nombre_consultado=asked,
        respuesta=answer,
    )
    assert context["identidad_verificada"] is False
    assert context["datos_comunicables"] is None

    single = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))
    assert single["has_offer"] is False
    assert single["motivo"] == "IDENTIDAD_NO_VERIFICADA"
    assert single["importe_total"] == 0  # ni siquiera el monto de la deuda


# ---------------------------------------------------------------- sin oferta


def test_without_a_matching_rule_the_full_amount_is_returned(
    agent: TestClient, laura: TestClient
) -> None:
    upload(laura, [invoice_row(amount="120000", due_date="2026-09-10")])  # sin reglas
    laura.post("/cases/generate")
    case = laura.get("/cases").json()["items"][0]
    verify_identity(agent, case)

    single = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))
    assert (single["has_offer"], single["oferta_id"], single["motivo"]) == (
        False,
        "SIN-OFERTA",
        "SIN_REGLA",
    )
    assert (single["importe_original"], single["descuento"], single["importe_total"]) == (
        120000,
        0,
        120000,
    )
    assert single["ofertas_restantes"] == 0

    plan = tool(agent, "obtener_oferta_cuotas_v2", **ids(case))
    assert (plan["importe_total"], plan["cantidad_cuotas"]) == (120000, 0)


def test_a_rule_without_installments(agent: TestClient, laura: TestClient) -> None:
    laura.post("/negotiation-rules", json=rule_body(max_installments=1))
    upload(laura, [invoice_row(amount="120000", due_date="2026-09-10")])
    laura.post("/cases/generate")
    case = laura.get("/cases").json()["items"][0]

    assert verify_identity(agent, case)["ofertas_restantes"] == 1
    plan = tool(agent, "obtener_oferta_cuotas_v2", **ids(case))
    assert (plan["has_offer"], plan["motivo"]) == (False, "SIN_CUOTAS")


# ---------------------------------------------------------------- registro


def _register(agent: TestClient, case: dict[str, Any], **overrides: Any) -> Any:
    params = {
        **ids(case),
        "resultado": "ACUERDO",
        "oferta_id": "PAGO-UNICO",
        "confirmacion_final": True,
        "cantidad_desconocimientos": 0,
    }
    params.update(overrides)
    return tool(agent, "registrar_resultado_v2", **params)


def test_an_agreement_on_an_offer_never_presented_is_not_registered(
    agent: TestClient, laura: TestClient, case: dict[str, Any]
) -> None:
    verify_identity(agent, case)  # identidad OK, pero el agente no pidió ninguna oferta

    result = _register(agent, case, oferta_id="PAGO-UNICO")

    assert (result["registrado"], result["motivo"]) == (False, "OFERTA_NO_OFRECIDA")
    assert case_status(laura, case) == "pending"


def test_an_agreement_needs_the_final_confirmation(
    agent: TestClient, laura: TestClient, case: dict[str, Any]
) -> None:
    verify_identity(agent, case)
    tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))

    result = _register(agent, case, confirmacion_final=False)

    assert (result["registrado"], result["motivo"]) == (False, "ACUERDO_SIN_CONFIRMAR")
    assert case_status(laura, case) == "pending"


def test_registering_twice_is_safe(agent: TestClient, case: dict[str, Any]) -> None:
    verify_identity(agent, case)
    tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))

    first = _register(agent, case)
    retry = _register(agent, case)  # ElevenLabs reintenta
    other = _register(agent, case, resultado="DERIVACION_HUMANA", oferta_id=None)

    assert first["registrado"] and retry["registrado"]
    assert (other["registrado"], other["motivo"]) == (False, "YA_REGISTRADO")


@pytest.mark.parametrize(
    ("result", "status"),
    [
        ("CONTACTADO", "contacted"),
        ("DESCONOCIMIENTO", "disputed"),
        ("DERIVACION_HUMANA", "escalated"),
    ],
)
def test_each_result_moves_the_case_to_its_status(
    agent: TestClient, laura: TestClient, case: dict[str, Any], result: str, status: str
) -> None:
    verify_identity(agent, case)

    answer = _register(agent, case, resultado=result, oferta_id=None, cantidad_desconocimientos=1)

    assert answer["registrado"] is True
    assert case_status(laura, case) == status
    [call] = laura.get(f"/cases/{case['id']}/conversations").json()
    assert (call["result"], call["unknown_count"], call["agreement"]) == (result, 1, None)


def test_a_contacted_case_can_be_called_again(agent: TestClient, case: dict[str, Any]) -> None:
    verify_identity(agent, case)
    _register(agent, case, resultado="CONTACTADO", oferta_id=None)

    verify_identity(agent, case, call="segunda-llamada")
    single = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case, "segunda-llamada"))

    assert single["has_offer"] is True


def test_a_case_with_an_agreement_is_no_longer_negotiable(
    agent: TestClient, case: dict[str, Any]
) -> None:
    verify_identity(agent, case)
    tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))
    _register(agent, case)

    verify_identity(agent, case, call="otra")
    single = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case, "otra"))
    late = _register(agent, case, conversation_id="otra", resultado="CONTACTADO", oferta_id=None)

    assert (single["has_offer"], single["motivo"]) == (False, "CASO_NO_NEGOCIABLE")
    assert (late["registrado"], late["motivo"]) == (False, "CASO_NO_NEGOCIABLE")


def test_offers_stay_fixed_during_the_call_even_if_a_rule_changes(
    agent: TestClient, laura: TestClient, case: dict[str, Any]
) -> None:
    verify_identity(agent, case)
    tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))  # 10 % -> 108.000
    rule = laura.get("/negotiation-rules").json()[0]
    laura.put(
        f"/negotiation-rules/{rule['id']}", json=rule_body(name="Corto plazo", discount_pct="20")
    )

    again = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))
    _register(agent, case)

    assert again["importe_total"] == 108000  # lo que el deudor ya escuchó
    [call] = laura.get(f"/cases/{case['id']}/conversations").json()
    assert call["agreement"]["total_amount"] == "108000.00"

    # Una llamada NUEVA sí usa la regla nueva... pero este caso ya tiene acuerdo.
    # Se prueba con otra conversación ANTES de registrar: ver el test siguiente.


def test_a_new_call_uses_the_current_rules(
    agent: TestClient, laura: TestClient, case: dict[str, Any]
) -> None:
    verify_identity(agent, case)
    tool(agent, "obtener_oferta_pago_unico_v2", **ids(case))
    rule = laura.get("/negotiation-rules").json()[0]
    laura.put(
        f"/negotiation-rules/{rule['id']}", json=rule_body(name="Corto plazo", discount_pct="20")
    )

    verify_identity(agent, case, call="nueva")
    fresh = tool(agent, "obtener_oferta_pago_unico_v2", **ids(case, "nueva"))

    assert fresh["importe_total"] == 96000


# ---------------------------------------------------------------- errores y seguridad


def test_unknown_case(agent: TestClient) -> None:
    response = agent.post(
        "/agent/tools/obtener_oferta_pago_unico_v2",
        json={"caso_id": "99999", "conversation_id": CALL},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "CASE_NOT_FOUND"


def test_a_conversation_cannot_jump_to_another_case(
    agent: TestClient, laura: TestClient, case: dict[str, Any]
) -> None:
    upload(
        laura,
        [invoice_row(external_id="R-1", debtor_name="Ricardo Pérez", debtor_document="20123456")],
    )
    laura.post("/cases/generate")
    other = next(c for c in laura.get("/cases").json()["items"] if c["id"] != case["id"])
    verify_identity(agent, case)

    response = agent.post("/agent/tools/obtener_oferta_pago_unico_v2", json=ids(other))

    assert response.status_code == 409
    assert response.json()["code"] == "CONVERSATION_OF_OTHER_CASE"


@pytest.mark.parametrize("header", [None, "Bearer token-equivocado", AGENT_TOKEN[:-1]])
def test_the_tools_need_the_agent_token(app: FastAPI, header: str | None) -> None:
    client = TestClient(app)
    if header is not None:
        client.headers["Authorization"] = header
    response = client.post("/agent/tools/obtener_oferta_pago_unico_v2", json={})
    assert response.status_code == 401


def test_the_token_also_works_without_the_bearer_prefix(app: FastAPI, case: dict[str, Any]) -> None:
    client = TestClient(app)
    client.headers["Authorization"] = AGENT_TOKEN
    response = client.post("/agent/tools/obtener_oferta_pago_unico_v2", json=ids(case))
    assert response.status_code == 200


def test_tools_are_off_until_the_token_is_configured(
    settings: Settings, database: Database
) -> None:
    app = create_app(settings.model_copy(update={"agent_tools_token": None}), database=database)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {AGENT_TOKEN}"

    response = client.post("/agent/tools/obtener_oferta_pago_unico_v2", json={})

    assert response.status_code == 503
    assert response.json()["code"] == "AGENT_TOOLS_DISABLED"


def test_the_agent_token_does_not_open_the_rest_of_the_api(agent: TestClient) -> None:
    assert agent.get("/cases").status_code == 401


# ---------------------------------------------------------------- vista del operador


def test_supervisor_can_see_calls_but_another_company_cannot(
    app: FastAPI,
    database: Database,
    fibrasur: CompanyWithAdmin,
    agent: TestClient,
    case: dict[str, Any],
) -> None:
    verify_identity(agent, case)
    make_user(database, fibrasur, "martin@fibrasur.com", UserRole.SUPERVISOR)
    make_company(database, "AguaNorte", admin_email="jefa@aguanorte.com")

    martin = logged_client(app, "martin@fibrasur.com")
    agua = logged_client(app, "jefa@aguanorte.com")

    assert len(martin.get(f"/cases/{case['id']}/conversations").json()) == 1
    assert agua.get(f"/cases/{case['id']}/conversations").status_code == 404


def test_case_status_is_not_changed_by_a_rejected_registration(
    agent: TestClient, database: Database, laura: TestClient, case: dict[str, Any]
) -> None:
    with database.session() as session:  # el caso ya está cerrado por otro medio
        session.execute(update(CaseModel).values(status=CaseStatus.CLOSED))
        session.commit()
    verify_identity(agent, case)

    late = _register(agent, case, resultado="DERIVACION_HUMANA", oferta_id=None)

    assert (late["registrado"], late["motivo"]) == (False, "CASO_NO_NEGOCIABLE")
    assert case_status(laura, case) == "closed"


def test_the_request_sent_by_elevenlabs_in_the_first_real_test(
    agent: TestClient, case: dict[str, Any]
) -> None:
    # Igual a lo que llegó en la prueba real: GET, y en `respuesta` todo el historial.
    params = {
        "caso_id": str(case["number"]),
        "conversation_id": "conv_0601m5ae2p5fevb8drc4y7t5m4sm",
        "nombre_consultado": "Ana Torres",
        "respuesta": ELEVENLABS_HISTORY.replace("Ricardo Perez", "Ana Torres"),
    }
    response = agent.get("/agent/tools/obtener_contexto_del_caso_v2", params=params)
    assert response.json()["identidad_verificada"] is True


def test_swagger_offers_an_authorize_button_for_the_agent_token(app: FastAPI) -> None:
    # Un campo común "Authorization" no sirve en Swagger (lo ignora). Con el
    # esquema de seguridad declarado, Swagger muestra "Authorize" y lo manda.
    spec = app.openapi()
    assert spec["components"]["securitySchemes"]["AgentToken"]["scheme"] == "bearer"
    operation = spec["paths"]["/agent/tools/obtener_contexto_del_caso_v2"]["get"]
    assert {"AgentToken": []} in operation["security"]
    assert "authorization" not in [p["name"].lower() for p in operation.get("parameters", [])]
