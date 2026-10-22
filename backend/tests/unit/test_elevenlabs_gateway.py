"""El adaptador del SDK de ElevenLabs, con un servidor HTTP falso.

No sale a internet: `httpx.MockTransport` responde en lugar de ElevenLabs. Sirve
para comprobar QUÉ manda el SDK oficial por la red y cómo se lee la respuesta.
"""

import json

import httpx
import pytest

from mavic.modules.voice.domain.call_gateway import CallGatewayError
from mavic.modules.voice.infrastructure.elevenlabs_calls import ElevenLabsCallGateway


def gateway(handler: object) -> tuple[ElevenLabsCallGateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)  # type: ignore[operator, no-any-return]

    client = httpx.Client(transport=httpx.MockTransport(record))
    return (
        ElevenLabsCallGateway(
            api_key="clave-de-prueba",
            agent_id="agent_gestion",
            phone_number_id="phnum_twilio",
            http_client=client,
        ),
        seen,
    )


def test_the_request_has_agent_number_branch_and_variables() -> None:
    elevenlabs, seen = gateway(
        lambda _: httpx.Response(
            200,
            json={
                "success": True,
                "message": "Success",
                "conversation_id": "conv_123",
                "callSid": "CA123",
            },
        )
    )

    result = elevenlabs.start_call(
        to_number="+5491155550102",
        dynamic_variables={"caso_id": "1042", "monto_total": 120000.5},
        branch_id="rama_prueba",
    )

    [request] = seen
    assert request.url.path == "/v1/convai/twilio/outbound-call"
    assert request.headers["xi-api-key"] == "clave-de-prueba"
    assert json.loads(request.content) == {
        "agent_id": "agent_gestion",
        "agent_phone_number_id": "phnum_twilio",
        "to_number": "+5491155550102",
        "conversation_initiation_client_data": {
            "dynamic_variables": {"caso_id": "1042", "monto_total": 120000.5},
            "branch_id": "rama_prueba",
        },
    }
    assert (result.accepted, result.conversation_id, result.call_sid) == (True, "conv_123", "CA123")


def test_without_branch_the_field_is_not_sent() -> None:
    elevenlabs, seen = gateway(
        lambda _: httpx.Response(200, json={"success": True, "message": "ok"})
    )

    elevenlabs.start_call(to_number="+5491155550102", dynamic_variables={}, branch_id=None)

    body = json.loads(seen[0].content)
    assert "branch_id" not in body["conversation_initiation_client_data"]


def test_an_http_error_becomes_a_readable_gateway_error() -> None:
    elevenlabs, _ = gateway(
        lambda _: httpx.Response(
            401, json={"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
        )
    )

    with pytest.raises(CallGatewayError) as error:
        elevenlabs.start_call(to_number="+5491155550102", dynamic_variables={}, branch_id=None)

    assert str(error.value) == "HTTP 401: Invalid API key"
    assert "clave-de-prueba" not in str(error.value)


def test_no_connection_is_a_gateway_error() -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    elevenlabs, _ = gateway(offline)

    with pytest.raises(CallGatewayError) as error:
        elevenlabs.start_call(to_number="+5491155550102", dynamic_variables={}, branch_id=None)

    assert str(error.value) == "sin conexión con ElevenLabs (ConnectError)"
