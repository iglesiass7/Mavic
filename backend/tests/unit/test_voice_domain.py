from datetime import date
from decimal import Decimal

import pytest

from mavic.modules.negotiation.domain.offers import build_offers
from mavic.modules.negotiation.domain.rules import PaymentTerms
from mavic.modules.voice.domain.call_offers import CallOffers, OfferProgress
from mavic.modules.voice.domain.identity import identity_verified
from mavic.modules.voice.domain.outcomes import CallResult, Rejection, check_registration
from mavic.modules.voice.infrastructure import offer_codec

# ---------------------------------------------------------------- identidad


@pytest.mark.parametrize(
    ("asked", "answer", "expected"),
    [
        ("Ricardo Pérez", "sí", True),
        ("ricardo perez", "Sí, soy yo", True),
        ("Ricardo", "si", True),  # alcanza con el nombre de pila
        ("Ricardo Pérez", True, True),  # el agente puede mandar un booleano
        ("Ricardo Pérez", "no", False),
        ("Ricardo Pérez", "", False),
        ("Ana Torres", "sí", False),  # preguntó por otra persona
        ("", "sí", False),
    ],
)
def test_identity_is_verified_only_with_the_right_name_and_a_yes(
    asked: str, answer: str | bool, expected: bool
) -> None:
    assert identity_verified(asked, answer, "Ricardo Pérez") is expected


# ---------------------------------------------------------------- registro de resultados


def _check(result: CallResult, **overrides: object) -> Rejection | None:
    values: dict[str, object] = {
        "identity_verified": True,
        "final_confirmation": True,
        "offer_id": "PAGO-UNICO",
        "offered_ids": frozenset({"PAGO-UNICO"}),
    }
    values.update(overrides)
    return check_registration(result, **values)  # type: ignore[arg-type]


def test_a_confirmed_agreement_on_an_offered_offer_is_accepted() -> None:
    assert _check(CallResult.ACUERDO) is None


@pytest.mark.parametrize(
    ("overrides", "rejection"),
    [
        ({"identity_verified": False}, Rejection.IDENTIDAD_NO_VERIFICADA),
        ({"final_confirmation": False}, Rejection.ACUERDO_SIN_CONFIRMAR),
        ({"offer_id": "CUOTAS-12-SIN-INTERES"}, Rejection.OFERTA_NO_OFRECIDA),  # inventada
        ({"offer_id": None}, Rejection.OFERTA_NO_OFRECIDA),
        ({"offered_ids": frozenset()}, Rejection.OFERTA_NO_OFRECIDA),  # nunca se ofreció
    ],
)
def test_agreements_that_are_not_safe_are_rejected(
    overrides: dict[str, object], rejection: Rejection
) -> None:
    assert _check(CallResult.ACUERDO, **overrides) is rejection


def test_disputing_a_debt_needs_the_debtor() -> None:
    assert _check(CallResult.DESCONOCIMIENTO, identity_verified=False) is (
        Rejection.IDENTIDAD_NO_VERIFICADA
    )


@pytest.mark.parametrize("result", [CallResult.CONTACTADO, CallResult.DERIVACION_HUMANA])
def test_contact_and_escalation_need_nothing_else(result: CallResult) -> None:
    assert _check(result, identity_verified=False, final_confirmation=False, offer_id=None) is None


# ---------------------------------------------------------------- ofertas de la llamada


def _offers(max_installments: int = 3) -> CallOffers:
    built = build_offers(
        PaymentTerms(Decimal("10"), 5, max_installments, Decimal("0")),
        Decimal("120000"),
        date(2026, 10, 16),
    )
    return CallOffers(
        total_amount=Decimal("120000"),
        currency="ARS",
        rule_name="Corto plazo",
        no_offer_reason=None,
        single_payment=built.single_payment,
        installments=built.installments,
    )


def test_remaining_offers_go_down_as_the_agent_presents_them() -> None:
    offers = _offers()
    assert OfferProgress(offers, False, False).remaining == 2
    assert OfferProgress(offers, True, False).remaining == 1
    assert OfferProgress(offers, True, True).remaining == 0
    assert OfferProgress(_offers(max_installments=1), False, False).remaining == 1


def test_only_presented_offers_can_be_accepted() -> None:
    progress = OfferProgress(_offers(), single_offered=True, installments_offered=False)
    assert progress.offered_ids == {"PAGO-UNICO"}


def test_offers_survive_the_trip_to_the_database_exactly() -> None:
    offers = _offers()
    assert offer_codec.decode(offer_codec.encode(offers)) == offers
