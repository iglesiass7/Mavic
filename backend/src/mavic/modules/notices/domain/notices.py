"""Avisos al deudor antes de que la factura pase a mora (ADR-038).

Hay dos momentos, como en Rynx:

    hoy ─────────── vence en 1..N días ──────────── vence hoy ──────── vencida
          PREVENTIVO (aviso "vence pronto")      DÍA DE VENCIMIENTO      (caso: el agente llama)
          grupo 1 de Facturas                     grupo 2 de Facturas      grupo 3

Cada empresa configura cada momento: el canal (email o WhatsApp), la hora del
envío automático, cuántos días antes (solo el preventivo) y el texto, con
"marcadores" que Mavic reemplaza por los datos de cada factura:

    "Hola {nombre}, tu factura {numero_factura} vence el {vencimiento}."
      ──>  "Hola Ana Torres, tu factura FS-1004 vence el 25/10/2026."

Una factura recibe cada aviso UNA sola vez (lo garantiza la base).
"""

import re
import uuid
from dataclasses import dataclass, replace
from datetime import date, time, timedelta
from decimal import Decimal
from enum import StrEnum

from mavic.core.errors import BusinessRuleViolationError


class NoticeStage(StrEnum):
    PREVENTIVE = "preventive"  # antes del vencimiento
    DUE_TODAY = "due_today"  # el día del vencimiento


class Channel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


# ---------------------------------------------------------------- marcadores

# Los datos que se pueden poner en el texto. El nombre es el que escribe la persona.
PLACEHOLDERS: dict[str, str] = {
    "nombre": "Nombre del deudor",
    "empresa": "Nombre de tu empresa",
    "numero_factura": "Número de la factura",
    "concepto": "Concepto de la factura",
    "monto": "Monto con la moneda ($ 18.500,00)",
    "vencimiento": "Fecha de vencimiento (dd/mm/aaaa)",
    "dias": "Días que faltan para el vencimiento",
    "instrucciones": "El texto de 'Cómo pagar' de este aviso",
}

_MARK = re.compile(r"\{([^{}]*)\}")

# Plantillas de WhatsApp aprobadas por Meta (Twilio Content): las variables van
# numeradas, siempre en este orden.
TEMPLATE_VARIABLES = ["nombre", "numero_factura", "monto", "vencimiento", "empresa"]

MAX_MESSAGE = 1600  # el límite de un WhatsApp; para el email también alcanza
MAX_SUBJECT = 150
MAX_INSTRUCTIONS = 500
MAX_DAYS_BEFORE = 30
_CONTENT_SID = re.compile(r"^HX[0-9a-fA-F]{32}$")


def unknown_placeholders(text: str) -> list[str]:
    """Los marcadores que no existen ("{nombr}"), para avisar antes de guardar.

    >>> unknown_placeholders("Hola {nombre}, debés {monto} {nombr}")
    ['nombr']
    """
    return [name for name in _MARK.findall(text) if name not in PLACEHOLDERS]


def render(text: str, values: dict[str, str]) -> str:
    """Reemplaza cada {marcador} por su valor. No interpreta nada más del texto.

    >>> render("Hola {nombre}: {monto}", {"nombre": "Ana", "monto": "$ 10,00"})
    'Hola Ana: $ 10,00'
    """
    return _MARK.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def format_money(amount: Decimal, currency: str) -> str:
    """Como se lee en Argentina: "$ 18.500,00" (o "USD 1.200,50").

    >>> format_money(Decimal("18500"), "ARS")
    '$ 18.500,00'
    >>> format_money(Decimal("1200.5"), "USD")
    'USD 1.200,50'
    """
    integer, decimals = f"{amount:,.2f}".split(".")
    symbol = "$" if currency == "ARS" else currency
    return f"{symbol} {integer.replace(',', '.')},{decimals}"


@dataclass(frozen=True)
class InvoiceFacts:
    """Lo que hace falta de una factura y su deudor para armar el aviso."""

    invoice_id: uuid.UUID
    external_id: str
    description: str
    amount: Decimal
    currency: str
    due_date: date
    debtor_name: str
    debtor_email: str | None
    debtor_phone: str | None


def values_for(
    facts: InvoiceFacts, *, company: str, today: date, instructions: str
) -> dict[str, str]:
    return {
        "nombre": facts.debtor_name,
        "empresa": company,
        "numero_factura": facts.external_id,
        "concepto": facts.description,
        "monto": format_money(facts.amount, facts.currency),
        "vencimiento": f"{facts.due_date:%d/%m/%Y}",
        "dias": str((facts.due_date - today).days),
        "instrucciones": instructions,
    }


# ---------------------------------------------------------------- configuración


@dataclass(frozen=True)
class NoticeSettings:
    stage: NoticeStage
    enabled: bool  # envío automático todos los días
    channel: Channel
    send_time: time  # hora (argentina) del envío automático
    days_before: int  # solo el preventivo: con cuántos días de anticipación
    email_subject: str
    message: str
    instructions: str  # "Cómo pagar": lo que reemplaza a {instrucciones}
    whatsapp_template_sid: str | None  # plantilla aprobada (Twilio Content), opcional


DEFAULTS: dict[NoticeStage, NoticeSettings] = {
    NoticeStage.PREVENTIVE: NoticeSettings(
        stage=NoticeStage.PREVENTIVE,
        enabled=False,
        channel=Channel.EMAIL,
        send_time=time(9, 0),
        days_before=5,
        email_subject="Tu factura {numero_factura} vence el {vencimiento}",
        message=(
            "Hola {nombre}:\n\n"
            "Te recordamos que tu factura {numero_factura} ({concepto}) por {monto} "
            "vence el {vencimiento}.\n\n"
            "{instrucciones}\n\n"
            "Si ya la pagaste, no hace falta que hagas nada.\n\n"
            "Saludos,\n{empresa}"
        ),
        instructions="",
        whatsapp_template_sid=None,
    ),
    NoticeStage.DUE_TODAY: NoticeSettings(
        stage=NoticeStage.DUE_TODAY,
        enabled=False,
        channel=Channel.WHATSAPP,
        send_time=time(9, 0),
        days_before=0,
        email_subject="Tu factura {numero_factura} vence hoy",
        message=(
            "Hola {nombre}, te escribimos de {empresa}. Tu factura {numero_factura} "
            "por {monto} vence hoy ({vencimiento}).\n\n"
            "{instrucciones}\n\n"
            "Si ya la pagaste, ignorá este mensaje."
        ),
        instructions="",
        whatsapp_template_sid=None,
    ),
}


def validate(settings: NoticeSettings) -> NoticeSettings:
    """Revisa y limpia la configuración. Lanza un error que dice qué corregir."""
    message = settings.message.strip()
    subject = settings.email_subject.strip()
    instructions = settings.instructions.strip()
    sid = (settings.whatsapp_template_sid or "").strip() or None

    def fail(text: str, code: str) -> BusinessRuleViolationError:
        return BusinessRuleViolationError(text, code=code)

    if not message:
        raise fail("Escribí el mensaje.", "NOTICE_MESSAGE_EMPTY")
    if len(message) > MAX_MESSAGE:
        raise fail(
            f"El mensaje puede tener hasta {MAX_MESSAGE} caracteres.", "NOTICE_MESSAGE_TOO_LONG"
        )
    if len(instructions) > MAX_INSTRUCTIONS:
        raise fail(
            f"'Cómo pagar' puede tener hasta {MAX_INSTRUCTIONS} caracteres.",
            "NOTICE_INSTRUCTIONS_TOO_LONG",
        )
    if settings.channel is Channel.EMAIL:
        if not subject:
            raise fail("Escribí el asunto del email.", "NOTICE_SUBJECT_EMPTY")
        if len(subject) > MAX_SUBJECT:
            raise fail(
                f"El asunto puede tener hasta {MAX_SUBJECT} caracteres.", "NOTICE_SUBJECT_TOO_LONG"
            )
    for text in (message, subject):
        wrong = unknown_placeholders(text)
        if wrong:
            names = ", ".join("{" + w + "}" for w in wrong)
            valid = ", ".join("{" + p + "}" for p in PLACEHOLDERS)
            raise fail(f"No existe {names}. Podés usar: {valid}.", "NOTICE_UNKNOWN_PLACEHOLDER")
    if (
        settings.stage is NoticeStage.PREVENTIVE
        and not 1 <= settings.days_before <= MAX_DAYS_BEFORE
    ):
        raise fail(
            f"Los días de anticipación van de 1 a {MAX_DAYS_BEFORE}.", "NOTICE_DAYS_BEFORE_INVALID"
        )
    if sid is not None and not _CONTENT_SID.match(sid):
        raise fail(
            "La plantilla de WhatsApp es un código que empieza con HX y sigue con 32 letras "
            "y números (lo da Twilio al aprobarla).",
            "NOTICE_TEMPLATE_SID_INVALID",
        )
    return replace(
        settings,
        message=message,
        email_subject=subject,
        instructions=instructions,
        whatsapp_template_sid=sid,
        days_before=settings.days_before if settings.stage is NoticeStage.PREVENTIVE else 0,
    )


# ---------------------------------------------------------------- a quién le toca


@dataclass(frozen=True)
class DueWindow:
    """Las facturas que vencen entre `first` y `last` (los dos incluidos)."""

    first: date
    last: date


def window_for(settings: NoticeSettings, today: date) -> DueWindow:
    """Qué facturas reciben el aviso hoy.

    Preventivo con 5 días: las que vencen de mañana a dentro de 5 días. Si un
    día no se envió (o la factura se cargó tarde), igual le llega antes de vencer.

    >>> s = DEFAULTS[NoticeStage.PREVENTIVE]
    >>> window_for(s, date(2026, 10, 16))
    DueWindow(first=datetime.date(2026, 10, 17), last=datetime.date(2026, 10, 21))
    >>> window_for(DEFAULTS[NoticeStage.DUE_TODAY], date(2026, 10, 16))
    DueWindow(first=datetime.date(2026, 10, 16), last=datetime.date(2026, 10, 16))
    """
    if settings.stage is NoticeStage.DUE_TODAY:
        return DueWindow(today, today)
    return DueWindow(today + timedelta(days=1), today + timedelta(days=settings.days_before))


def recipient_for(channel: Channel, facts: InvoiceFacts) -> str | None:
    """El email o el teléfono del deudor, según el canal (None si no tiene)."""
    value = facts.debtor_email if channel is Channel.EMAIL else facts.debtor_phone
    return value.strip() if value and value.strip() else None
