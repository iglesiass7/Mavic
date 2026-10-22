"""Lo que recibe el agente al empezar una llamada saliente (ADR-034).

El agente "Gestión de Deuda" no consulta a Mavic durante la llamada: recibe
TODO antes de empezar, en 8 variables dinámicas con estos nombres exactos
(el contrato que definió quien arma el agente):

    caso_id           "1042"                    texto; para cruzar el webhook con el caso
    nombre            "Ana Torres"              a quién se llama
    nombre_acreedor   "FibraSur"                la empresa
    cantidad_deudas   2                         = largo de `deudas`
    monto_total       120000                    = suma de `deudas`, una sola moneda
    moneda_total      "pesos argentinos"        lista para decir en voz alta
    deudas            '[{"deuda_id": ...}]'     lista JSON EN TEXTO
    ofertas           '[{"prioridad": 0, ...}]' lista JSON EN TEXTO, en orden

Por qué `deudas` y `ofertas` van como texto: ElevenLabs solo acepta variables
de tipo texto, número o booleano. Una lista viaja serializada.

Los montos: Decimal en todo Mavic; recién acá, en el borde, pasan a número de
JSON. Antes se verifica que el número diga EXACTAMENTE lo mismo que el Decimal.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from mavic.modules.negotiation.domain.offers import CallOffer, OfferKind

SCHEMA_VERSION = 2  # 1 = flujo con herramientas; 2 = variables al iniciar

# Nombres exactos de las variables (distingue mayúsculas): ni una más, ni una menos.
VARIABLE_NAMES = (
    "caso_id",
    "nombre",
    "nombre_acreedor",
    "cantidad_deudas",
    "monto_total",
    "moneda_total",
    "deudas",
    "ofertas",
)

# Cómo se dice cada moneda. Una moneda que no está acá no se puede llamar.
SPOKEN_CURRENCY = {"ARS": "pesos argentinos"}


def case_number_from_reference(case_reference: str) -> int | None:
    """El número de caso. Acepta "1042" y también formatos con prefijo como "CASO-1042".

    >>> [case_number_from_reference(x) for x in ["1042", " CASO-1042 ", "abc", ""]]
    [1042, 1042, None, None]
    """
    match = re.fullmatch(r"\D*(\d{1,18})", case_reference.strip())
    return int(match.group(1)) if match else None


class CallPayloadError(ValueError):
    """Los datos no cumplen el contrato del agente: la llamada no se inicia."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DebtLine:
    """Una factura del caso, tal como la recibe el agente."""

    debt_id: str  # número de factura: identifica, el agente no lo lee
    reason: str  # descripción breve: "Abono internet octubre"
    amount: Decimal
    currency: str  # código ISO: ARS


def spoken_currency(code: str) -> str:
    """La moneda como se dice en voz alta.

    >>> spoken_currency("ARS")
    'pesos argentinos'
    """
    try:
        return SPOKEN_CURRENCY[code]
    except KeyError:
        raise CallPayloadError(
            "UNSUPPORTED_CURRENCY", f"No se puede llamar por una deuda en {code}."
        ) from None


def json_amount(value: Decimal) -> int | float:
    """Un monto como número de JSON, sin perder un centavo.

    >>> json_amount(Decimal("70000.00")), json_amount(Decimal("57866.67"))
    (70000, 57866.67)
    """
    if value == value.to_integral_value():
        return int(value)
    number = float(value)
    # El float se escribe en JSON con repr(): tiene que volver al MISMO Decimal.
    if Decimal(repr(number)) != value.quantize(Decimal("0.01")):
        raise CallPayloadError("AMOUNT_NOT_EXACT", f"El monto {value} no se puede enviar exacto.")
    return number


def _offer_json(offer: CallOffer, spoken: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "prioridad": offer.priority,
        "oferta_id": offer.offer_id,
        "tipo": offer.kind.value,
        "moneda": spoken,
        "importe_total": json_amount(offer.total_amount),
    }
    if offer.discount_pct is not None and offer.discount_amount is not None:
        item["descuento_porcentaje"] = json_amount(offer.discount_pct)
        item["descuento"] = json_amount(offer.discount_amount)
    if offer.kind is OfferKind.INSTALLMENTS:
        item["cantidad_cuotas"] = offer.installment_count
        assert offer.installment_amount is not None  # noqa: S101 - lo garantiza _check_offers
        item["importe_cuota"] = json_amount(offer.installment_amount)
    return item


def _check_offers(offers: list[CallOffer]) -> None:
    ids = [offer.offer_id for offer in offers]
    if len(set(ids)) != len(ids):
        raise CallPayloadError("DUPLICATED_OFFER", "Hay dos ofertas con el mismo id.")
    for index, offer in enumerate(offers):
        if offer.priority != index:
            raise CallPayloadError(
                "OFFER_ORDER", "La prioridad tiene que coincidir con la posición."
            )
        # Un solo importe de cuota: solo vale si TODAS las cuotas son iguales.
        uneven = offer.kind is OfferKind.INSTALLMENTS and (
            offer.installment_count < 2
            or offer.installment_amount is None
            or offer.installment_amount * offer.installment_count != offer.total_amount
        )
        if uneven:
            raise CallPayloadError(
                "UNEVEN_INSTALLMENTS",
                f"La oferta {offer.offer_id}: cuotas x importe no da el total.",
            )


def build_dynamic_variables(
    *,
    case_number: int,
    debtor_name: str,
    creditor_name: str,
    currency: str,
    debts: list[DebtLine],
    offers: list[CallOffer],
) -> dict[str, str | int | float]:
    """Las 8 variables del contrato, validadas. Si algo no cierra, no se llama."""
    if not debts:
        raise CallPayloadError("NO_DEBTS", "El caso no tiene facturas.")
    if any(debt.currency != currency for debt in debts):
        # Nunca se suman pesos con dólares en un mismo total.
        raise CallPayloadError("MIXED_CURRENCIES", "El caso tiene facturas de otra moneda.")
    _check_offers(offers)
    spoken = spoken_currency(currency)

    debt_items = [
        {
            "deuda_id": debt.debt_id,
            "motivo": debt.reason,
            "monto": json_amount(debt.amount),
            "moneda": spoken,
        }
        for debt in debts
    ]
    offer_items = [_offer_json(offer, spoken) for offer in offers]
    variables: dict[str, str | int | float] = {
        "caso_id": str(case_number),
        "nombre": debtor_name,
        "nombre_acreedor": creditor_name,
        "cantidad_deudas": len(debt_items),
        "monto_total": json_amount(sum((debt.amount for debt in debts), Decimal(0))),
        "moneda_total": spoken,
        "deudas": json.dumps(debt_items, ensure_ascii=False, separators=(",", ":")),
        "ofertas": json.dumps(offer_items, ensure_ascii=False, separators=(",", ":")),
    }
    assert tuple(variables) == VARIABLE_NAMES  # noqa: S101 - el contrato no cambia por accidente
    return variables


# ---------------------------------------------------------------- la foto de la llamada


def offers_snapshot(offers: list[CallOffer]) -> list[dict[str, Any]]:
    """Las ofertas EXACTAS que escuchó el deudor, con montos como texto.

    Es la fuente de verdad del acuerdo: si el agente informa ACUERDO con una
    oferta, los números se copian de acá, no del texto de la llamada ni de las
    reglas de hoy (que pudieron cambiar).
    """
    return [
        {
            "priority": offer.priority,
            "offer_id": offer.offer_id,
            "kind": offer.kind.value,
            "total_amount": str(offer.total_amount),
            "discount_pct": None if offer.discount_pct is None else str(offer.discount_pct),
            "discount_amount": None
            if offer.discount_amount is None
            else str(offer.discount_amount),
            "installment_count": offer.installment_count,
            "installment_amount": None
            if offer.installment_amount is None
            else str(offer.installment_amount),
        }
        for offer in offers
    ]


@dataclass(frozen=True)
class SnapshotOffer:
    offer_id: str
    kind: OfferKind
    total_amount: Decimal
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    installment_count: int
    installment_amount: Decimal | None


def _decimal_or_none(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def find_snapshot_offer(snapshot: list[dict[str, Any]], offer_id: str) -> SnapshotOffer | None:
    """La oferta con ese id EXACTO dentro de la foto, o None."""
    for item in snapshot:
        if item.get("offer_id") == offer_id:
            return SnapshotOffer(
                offer_id=offer_id,
                kind=OfferKind(item["kind"]),
                total_amount=Decimal(item["total_amount"]),
                discount_pct=_decimal_or_none(item.get("discount_pct")),
                discount_amount=_decimal_or_none(item.get("discount_amount")),
                installment_count=int(item["installment_count"]),
                installment_amount=_decimal_or_none(item.get("installment_amount")),
            )
    return None
