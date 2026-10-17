"""Normalización y validación de cada tipo de dato que llega en un archivo.

Cada función recibe el valor "crudo" de una celda (texto, número o fecha, según
venga de un CSV o de un Excel) y devuelve el valor limpio, o lanza
`InvalidValueError` con un código y un mensaje para la persona que cargó el archivo.

Son funciones puras: misma entrada, misma salida, sin base de datos. Por eso
se pueden testear con decenas de casos en milisegundos.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import phonenumbers
from email_validator import EmailNotValidError, validate_email

# Región por defecto para interpretar teléfonos sin código de país.
DEFAULT_PHONE_REGION = "AR"
SUPPORTED_CURRENCIES = frozenset({"ARS"})
MAX_AMOUNT = Decimal("999999999999.99")  # entra en NUMERIC(14, 2)


class InvalidValueError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def clean_text(raw: object, *, max_length: int) -> str:
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise InvalidValueError("REQUIRED", "El campo es obligatorio.")
    if len(text) > max_length:
        raise InvalidValueError("TOO_LONG", f"No puede superar {max_length} caracteres.")
    return text


def parse_document(raw: object) -> str:
    """DNI o CUIT: se guardan solo los dígitos.

    "20.123.456" -> "20123456"   ·   "20-12345678-9" -> "20123456789"
    """
    text = clean_text(raw, max_length=30)
    if isinstance(raw, float) and raw.is_integer():  # Excel guarda 20123456 como 20123456.0
        text = str(int(raw))
    digits = re.sub(r"[.\-\s]", "", text)
    if not digits.isdigit() or not 6 <= len(digits) <= 11:
        raise InvalidValueError(
            "INVALID_DOCUMENT", f"El documento '{text}' no es válido (DNI o CUIT, solo números)."
        )
    return digits


def parse_phone(raw: object) -> str:
    """Teléfono en formato internacional E.164 (+5491122334455).

    El agente de voz llama a este número: un formato ambiguo es una llamada a
    la persona equivocada. Se usa libphonenumber (la librería de Google que usa
    Android) en vez de inventar reglas propias.
    """
    text = clean_text(raw, max_length=30)
    if isinstance(raw, float) and raw.is_integer():
        text = str(int(raw))
    try:
        number = phonenumbers.parse(text, DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException as exc:
        raise InvalidValueError("INVALID_PHONE", f"El teléfono '{text}' no es válido.") from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidValueError("INVALID_PHONE", f"El teléfono '{text}' no es válido.")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def parse_email(raw: object) -> str:
    text = clean_text(raw, max_length=254)
    try:
        # check_deliverability=False: no consulta DNS (sería lento e inestable).
        return validate_email(text, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise InvalidValueError("INVALID_EMAIL", f"El email '{text}' no es válido.") from exc


def parse_amount(raw: object) -> Decimal:
    """Monto con hasta 2 decimales. Acepta formato argentino y del Excel.

    "1234.56" · "1234,56" · "1.234,56" · 1234.56 (número de Excel) -> Decimal("1234.56")

    Se usa Decimal y no float: con float, 0.1 + 0.2 da 0.30000000000000004.
    En plata eso no es aceptable.
    """
    if isinstance(raw, bool):
        raise InvalidValueError("INVALID_AMOUNT", "El monto no es válido.")
    if isinstance(raw, int | float):
        # Excel guarda los números como float binario: 1234.56 puede llegar como
        # 1234.5600000000001. Se redondea a 6 decimales antes de validar.
        text = str(round(Decimal(repr(raw)), 6))
    else:
        text = clean_text(raw, max_length=30).replace("$", "").replace(" ", "")
        if "," in text and "." in text:  # 1.234,56 -> 1234.56
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:  # 1234,56 -> 1234.56
            text = text.replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise InvalidValueError("INVALID_AMOUNT", f"El monto '{raw}' no es un número.") from exc
    if not amount.is_finite() or amount <= 0:
        raise InvalidValueError("INVALID_AMOUNT", "El monto tiene que ser mayor a cero.")
    # Primero el tope: con un número gigante ("1e400"), redondear a centavos
    # haría fallar a la librería Decimal con un error inesperado (500).
    if amount > MAX_AMOUNT:
        raise InvalidValueError("INVALID_AMOUNT", "El monto es demasiado grande.")
    if amount != amount.quantize(Decimal("0.01")):
        raise InvalidValueError("INVALID_AMOUNT", "El monto puede tener como máximo 2 decimales.")
    return amount.quantize(Decimal("0.01"))


def parse_currency(raw: object) -> str:
    code = clean_text(raw, max_length=3).upper()
    if code not in SUPPORTED_CURRENCIES:
        raise InvalidValueError(
            "UNSUPPORTED_CURRENCY",
            f"Moneda '{code}' no soportada. Por ahora solo se aceptan facturas en ARS.",
        )
    return code


def parse_due_date(raw: object) -> date:
    """Fecha de vencimiento: AAAA-MM-DD, DD/MM/AAAA o una fecha de Excel."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = clean_text(raw, max_length=20)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise InvalidValueError(
        "INVALID_DATE", f"La fecha '{text}' no es válida. Usá AAAA-MM-DD o DD/MM/AAAA."
    )
