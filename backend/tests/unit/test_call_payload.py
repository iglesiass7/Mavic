"""El contrato de variables del agente nuevo (ADR-034), sin base de datos.

Cada test corresponde a una prueba pedida en el contrato de integración
(sección 12): payload exacto, serialización, prioridad, varias facturas,
monedas y cuotas que no se dividen exacto.
"""

import json
from decimal import Decimal

import pytest

from mavic.modules.negotiation.domain.offers import CallOffer, OfferKind, call_offer_list
from mavic.modules.negotiation.domain.rules import PaymentTerms
from mavic.modules.voice.domain.call_payload import (
    VARIABLE_NAMES,
    CallPayloadError,
    DebtLine,
    build_dynamic_variables,
    find_snapshot_offer,
    json_amount,
    offers_snapshot,
)

TERMS = PaymentTerms(
    discount_pct=Decimal("10"), payment_days=5, max_installments=6, interest_pct=Decimal("12")
)
DEBTS = [
    DebtLine("FAC-1001", "Factura de servicio vencida", Decimal("70000.00"), "ARS"),
    DebtLine("FAC-1002", "Saldo de financiación vencido", Decimal("50000.50"), "ARS"),
]


def variables(**overrides: object) -> dict[str, str | int | float]:
    arguments: dict[str, object] = {
        "case_number": 1042,
        "debtor_name": "Carla Ríos",
        "creditor_name": "FibraSur",
        "currency": "ARS",
        "debts": DEBTS,
        "offers": call_offer_list(TERMS, Decimal("120000.50")),
    }
    arguments.update(overrides)
    return build_dynamic_variables(**arguments)  # type: ignore[arg-type]


def test_the_payload_has_exactly_the_eight_variables_of_the_contract() -> None:
    result = variables()

    assert tuple(result) == VARIABLE_NAMES
    assert result["caso_id"] == "1042"  # texto, no número
    assert result["nombre"] == "Carla Ríos"
    assert result["nombre_acreedor"] == "FibraSur"
    assert result["moneda_total"] == "pesos argentinos"
    # Ningún nombre del contrato anterior.
    for old in ("case_id", "empresa", "monto", "moneda", "oferta_id", "confirmacion_final"):
        assert old not in result


def test_debts_and_offers_travel_as_json_text_in_utf8() -> None:
    result = variables()

    assert isinstance(result["deudas"], str) and isinstance(result["ofertas"], str)
    assert "financiación" in result["deudas"]  # sin ó: UTF-8 tal cual
    assert json.loads(result["deudas"]) == [
        {
            "deuda_id": "FAC-1001",
            "motivo": "Factura de servicio vencida",
            "monto": 70000,
            "moneda": "pesos argentinos",
        },
        {
            "deuda_id": "FAC-1002",
            "motivo": "Saldo de financiación vencido",
            "monto": 50000.5,
            "moneda": "pesos argentinos",
        },
    ]


def test_debt_count_and_total_match_the_debts() -> None:
    result = variables()

    debts = json.loads(str(result["deudas"]))
    assert result["cantidad_deudas"] == len(debts) == 2
    assert result["monto_total"] == 120000.5


def test_offers_keep_their_priority_order_and_fields() -> None:
    offers = json.loads(str(variables()["ofertas"]))

    assert [o["prioridad"] for o in offers] == [0, 1]
    single, plan = offers
    assert single == {
        "prioridad": 0,
        "oferta_id": "PAGO-UNICO",
        "tipo": "PAGO_UNICO",
        "moneda": "pesos argentinos",
        "importe_total": 108000.45,
        "descuento_porcentaje": 10,
        "descuento": 12000.05,
    }
    assert plan["tipo"] == "CUOTAS"
    assert plan["cantidad_cuotas"] == 6
    assert plan["cantidad_cuotas"] * Decimal(str(plan["importe_cuota"])) == Decimal(
        str(plan["importe_total"])
    )
    # Campos que el agente ya no usa: no se mandan.
    for old in ("fecha_limite_pago", "fecha_primera_cuota", "intereses", "cronograma"):
        assert old not in single and old not in plan


def test_a_rule_without_discount_sends_no_discount_fields() -> None:
    terms = PaymentTerms(
        discount_pct=Decimal("0"), payment_days=5, max_installments=1, interest_pct=Decimal("0")
    )
    offers = json.loads(
        str(variables(offers=call_offer_list(terms, Decimal("120000.50")))["ofertas"])
    )

    assert offers == [
        {
            "prioridad": 0,
            "oferta_id": "PAGO-UNICO",
            "tipo": "PAGO_UNICO",
            "moneda": "pesos argentinos",
            "importe_total": 120000.5,
        }
    ]


def test_installments_are_always_equal() -> None:
    """310.000 al 12 % en 6 cuotas: antes la última tenía 2 centavos más. Ahora son iguales."""
    plan = call_offer_list(TERMS, Decimal("310000"))[1]

    assert plan.installment_amount == Decimal("57866.67")
    assert plan.total_amount == plan.installment_amount * 6 == Decimal("347200.02")


def test_uneven_installments_are_rejected() -> None:
    uneven = CallOffer(
        priority=0,
        offer_id="CUOTAS-3-SIN-INTERES",
        kind=OfferKind.INSTALLMENTS,
        total_amount=Decimal("100.00"),
        discount_pct=None,
        discount_amount=None,
        installment_count=3,
        installment_amount=Decimal("33.33"),  # 3 x 33,33 = 99,99
    )
    with pytest.raises(CallPayloadError) as error:
        variables(offers=[uneven])
    assert error.value.code == "UNEVEN_INSTALLMENTS"


def test_currencies_are_never_mixed() -> None:
    dollars = DebtLine("U-1", "Equipo", Decimal("10"), "USD")
    with pytest.raises(CallPayloadError) as error:
        variables(debts=[*DEBTS, dollars])
    assert error.value.code == "MIXED_CURRENCIES"


def test_a_currency_without_spoken_name_cannot_be_called() -> None:
    dollars = [DebtLine("U-1", "Equipo", Decimal("10"), "USD")]
    with pytest.raises(CallPayloadError) as error:
        variables(debts=dollars, currency="USD")
    assert error.value.code == "UNSUPPORTED_CURRENCY"


def test_priorities_must_match_positions() -> None:
    offers = call_offer_list(TERMS, Decimal("1000"))
    with pytest.raises(CallPayloadError) as error:
        variables(offers=list(reversed(offers)))
    assert error.value.code == "OFFER_ORDER"


def test_amounts_become_json_numbers_without_losing_cents() -> None:
    assert json_amount(Decimal("70000.00")) == 70000
    assert json_amount(Decimal("0.10")) == 0.1
    assert json.dumps(json_amount(Decimal("57866.67"))) == "57866.67"


def test_the_snapshot_gives_back_the_exact_offer() -> None:
    offers = call_offer_list(TERMS, Decimal("310000"))
    snapshot = json.loads(json.dumps(offers_snapshot(offers)))  # como vuelve de la base

    plan = find_snapshot_offer(snapshot, "CUOTAS-6-CON-INTERES")

    assert plan is not None
    assert plan.total_amount == Decimal("347200.02")
    assert plan.installment_amount == Decimal("57866.67")
    assert find_snapshot_offer(snapshot, "OF-INVENTADA") is None
