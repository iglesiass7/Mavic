"""Los remitentes reales, sin salir a internet.

- Twilio: con un transporte de httpx falso, se mira el pedido EXACTO que saldría.
- SMTP: con un servidor SMTP de mentira (se reemplaza smtplib.SMTP).
"""

import json
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from mavic.modules.notices.domain.senders import DeliveryError, OutgoingMessage
from mavic.modules.notices.infrastructure.senders import SmtpEmailSender, TwilioWhatsAppSender

SID = "AC" + "0" * 32


def twilio(handler: Any) -> TwilioWhatsAppSender:
    client = httpx.Client(transport=httpx.MockTransport(handler), auth=(SID, "token"))
    return TwilioWhatsAppSender(
        account_sid=SID, auth_token="token", from_number="+14155238886", http_client=client
    )


def test_twilio_free_text_goes_as_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "SM123"})

    sid = twilio(handler).send(OutgoingMessage(to="+5491155550104", body="Hola"))

    assert sid == "SM123"
    [request] = seen
    assert str(request.url) == f"https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json"
    form = parse_qs(request.content.decode())
    assert form == {
        "From": ["whatsapp:+14155238886"],
        "To": ["whatsapp:+5491155550104"],
        "Body": ["Hola"],
    }


def test_twilio_template_goes_with_content_sid_and_variables() -> None:
    seen: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(parse_qs(request.content.decode()))
        return httpx.Response(201, json={"sid": "SM9"})

    twilio(handler).send(
        OutgoingMessage(
            to="+5491155550104",
            body="(no se usa)",
            template_sid="HX" + "a" * 32,
            template_variables={"1": "Lucía", "2": "FS-4"},
        )
    )

    [form] = seen
    assert "Body" not in form
    assert form["ContentSid"] == ["HX" + "a" * 32]
    assert json.loads(form["ContentVariables"][0]) == {"1": "Lucía", "2": "FS-4"}


def test_twilio_errors_explain_why_without_leaking_the_token() -> None:
    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 21211, "message": "Invalid 'To' Phone Number"})

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 20003, "message": "Authenticate"})

    with pytest.raises(DeliveryError, match="Twilio 21211: Invalid 'To' Phone Number"):
        twilio(rejected).send(OutgoingMessage(to="+1", body="x"))
    with pytest.raises(DeliveryError, match="TWILIO_ACCOUNT_SID") as info:
        twilio(unauthorized).send(OutgoingMessage(to="+1", body="x"))
    assert "token" not in str(info.value)


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host, self.port = host, port
        self.sent: list[EmailMessage] = []
        self.tls = self.logged_in = self.quit_called = False
        FakeSmtp.instances.append(self)

    def starttls(self, context: Any) -> None:
        self.tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = True

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def quit(self) -> None:
        self.quit_called = True


def test_smtp_reuses_one_connection_for_the_whole_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    sender = SmtpEmailSender(
        host="smtp.example.com",
        port=587,
        sender="FibraSur <avisos@fibrasur.com>",
        username="avisos@fibrasur.com",
        password="clave",
        security="starttls",
    )

    sender.send(OutgoingMessage(to="ana@example.com", subject="Vence", body="Hola Ana"))
    sender.send(OutgoingMessage(to="jorge@example.com", subject="Vence", body="Hola Jorge"))
    sender.close()

    [smtp] = FakeSmtp.instances
    assert smtp.tls and smtp.logged_in and smtp.quit_called
    first = smtp.sent[0]
    assert first["To"] == "ana@example.com"
    assert first["From"] == "FibraSur <avisos@fibrasur.com>"
    assert first.get_content().strip() == "Hola Ana"
    assert len(smtp.sent) == 2
