"""Remitentes reales: email por SMTP y WhatsApp por Twilio.

EMAIL (SMTP)
    Sirve cualquier servidor SMTP: Gmail con una "contraseña de aplicación" para
    probar, AWS SES en producción, o Mailpit en tu PC (docker compose lo levanta:
    los mails NO salen a internet, se ven en http://localhost:8025).
    Se abre UNA conexión por tanda y se reusa para todos los mails.

WHATSAPP (Twilio)
    POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
         From=whatsapp:+14155238886  To=whatsapp:+5491155550101  Body=...
    Para escribirle PRIMERO a alguien, WhatsApp exige una plantilla aprobada por
    Meta (ContentSid + ContentVariables). Sin plantilla, el texto libre solo llega
    si la persona escribió en las últimas 24 horas, o en el "sandbox" de prueba.

Las claves se leen del .env y nunca se escriben en un log ni en un error.
"""

import contextlib
import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Literal

import httpx

from mavic.modules.notices.domain.notices import Channel
from mavic.modules.notices.domain.senders import DeliveryError, MessageSender, OutgoingMessage

SmtpSecurity = Literal["starttls", "ssl", "none"]
TIMEOUT_SECONDS = 20


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str | None,
        password: str | None,
        security: SmtpSecurity,
    ) -> None:
        self._host, self._port, self._from = host, port, sender
        self._username, self._password, self._security = username, password, security
        self._smtp: smtplib.SMTP | None = None

    def _connect(self) -> smtplib.SMTP:
        context = ssl.create_default_context()
        if self._security == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, self._port, timeout=TIMEOUT_SECONDS, context=context
            )
        else:
            smtp = smtplib.SMTP(self._host, self._port, timeout=TIMEOUT_SECONDS)
            if self._security == "starttls":
                smtp.starttls(context=context)
        if self._username and self._password:
            smtp.login(self._username, self._password)
        return smtp

    def send(self, message: OutgoingMessage) -> str:
        email = EmailMessage()
        email["From"] = self._from
        email["To"] = message.to
        email["Subject"] = message.subject
        message_id = make_msgid(domain=self._from.rsplit("@", 1)[-1].strip(" >") or None)
        email["Message-ID"] = message_id
        email.set_content(message.body)  # texto plano, UTF-8
        try:
            if self._smtp is None:
                self._smtp = self._connect()
            self._smtp.send_message(email)
        except smtplib.SMTPRecipientsRefused as exc:
            raise DeliveryError("El servidor de email rechazó la dirección del deudor.") from exc
        except smtplib.SMTPAuthenticationError as exc:
            self.close()
            raise DeliveryError(
                "El servidor de email no aceptó el usuario o la contraseña (SMTP_USERNAME / "
                "SMTP_PASSWORD)."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            self.close()  # la próxima vuelve a conectarse
            raise DeliveryError(f"No se pudo mandar el email ({type(exc).__name__}).") from exc
        return message_id

    def close(self) -> None:
        if self._smtp is not None:
            with contextlib.suppress(smtplib.SMTPException, OSError):
                self._smtp.quit()
            self._smtp = None


class TwilioWhatsAppSender:
    API = "https://api.twilio.com/2010-04-01"

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._sid = account_sid
        self._from = from_number
        self._client = http_client or httpx.Client(
            auth=(account_sid, auth_token), timeout=TIMEOUT_SECONDS
        )

    def send(self, message: OutgoingMessage) -> str:
        data = {"From": f"whatsapp:{self._from}", "To": f"whatsapp:{message.to}"}
        if message.template_sid:
            data["ContentSid"] = message.template_sid
            data["ContentVariables"] = json.dumps(message.template_variables, ensure_ascii=False)
        else:
            data["Body"] = message.body
        try:
            response = self._client.post(
                f"{self.API}/Accounts/{self._sid}/Messages.json", data=data
            )
        except httpx.HTTPError as exc:
            raise DeliveryError(f"Twilio no respondió ({type(exc).__name__}).") from exc
        if response.status_code >= 400:
            raise DeliveryError(_twilio_error(response))
        sid = response.json().get("sid")
        return str(sid or "")

    def close(self) -> None:
        self._client.close()


def _twilio_error(response: httpx.Response) -> str:
    """El motivo que da Twilio, sin datos sensibles: "Twilio 21211: número inválido"."""
    try:
        body = response.json()
    except ValueError:
        return f"Twilio respondió {response.status_code}."
    code = body.get("code")
    text = str(body.get("message") or "").strip()
    if response.status_code == 401:
        return "Twilio no aceptó las credenciales (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)."
    return f"Twilio {code}: {text}" if code else f"Twilio respondió {response.status_code}: {text}"


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    sender: str  # "FibraSur <avisos@fibrasur.com>"
    username: str | None
    password: str | None
    security: SmtpSecurity


@dataclass(frozen=True)
class TwilioConfig:
    account_sid: str
    auth_token: str
    from_number: str  # el número de WhatsApp de Twilio, ej. +14155238886 (sandbox)


class ConfiguredSenders:
    """Arma los remitentes con lo que haya en el .env. Uno nuevo por tanda."""

    def __init__(self, *, smtp: SmtpConfig | None, twilio: TwilioConfig | None) -> None:
        self._smtp = smtp
        self._twilio = twilio

    def configured(self, channel: Channel) -> bool:
        return (self._smtp if channel is Channel.EMAIL else self._twilio) is not None

    def sender_for(self, channel: Channel) -> MessageSender | None:
        if channel is Channel.EMAIL and self._smtp is not None:
            c = self._smtp
            return SmtpEmailSender(
                host=c.host,
                port=c.port,
                sender=c.sender,
                username=c.username,
                password=c.password,
                security=c.security,
            )
        if channel is Channel.WHATSAPP and self._twilio is not None:
            t = self._twilio
            return TwilioWhatsAppSender(
                account_sid=t.account_sid, auth_token=t.auth_token, from_number=t.from_number
            )
        return None
