from datetime import date
from decimal import Decimal

import pytest

from mavic.modules.negotiation.domain.offers import (
    add_months,
    build_offers,
    split_in_installments,
)
from mavic.modules.negotiation.domain.rules import PaymentTerms

TODAY = date(2026, 10, 16)


def terms(
    discount: str = "10", days: int = 5, installments: int = 3, interest: str = "0"
) -> PaymentTerms:
    return PaymentTerms(
        discount_pct=Decimal(discount),
        payment_days=days,
        max_installments=installments,
        interest_pct=Decimal(interest),
    )


def test_examples_from_the_voice_agent_contract() -> None:
    # Los mismos números que los ejemplos que pasó quien arma el agente de ElevenLabs.
    offers = build_offers(terms(), Decimal("120000"), TODAY)

    single = offers.single_payment
    assert single.offer_id == "PAGO-UNICO"
    assert single.discount_amount == Decimal("12000.00")
    assert single.total_amount == Decimal("108000.00")

    plan = offers.installments
    assert plan is not None
    assert plan.offer_id == "CUOTAS-3-SIN-INTERES"
    assert plan.total_amount == Decimal("120000")
    assert plan.installment_amount == Decimal("40000.00")


def test_single_payment_deadline_uses_the_rule_days() -> None:
    offer = build_offers(terms(days=5), Decimal("1000"), TODAY).single_payment
    assert offer.pay_by == date(2026, 10, 21)


def test_installments_with_interest() -> None:
    plan = build_offers(terms(installments=6, interest="12"), Decimal("56900"), TODAY).installments
    assert plan is not None
    assert plan.offer_id == "CUOTAS-6-CON-INTERES"
    assert plan.interest_amount == Decimal("6828.00")
    assert plan.total_amount == Decimal("63728.00")
    assert sum(i.amount for i in plan.schedule) == plan.total_amount


def test_schedule_is_monthly_from_the_first_due_date() -> None:
    plan = build_offers(terms(days=5, installments=3), Decimal("900"), TODAY).installments
    assert plan is not None
    assert [i.due_date for i in plan.schedule] == [
        date(2026, 10, 21),
        date(2026, 11, 21),
        date(2026, 12, 21),
    ]
    assert [i.number for i in plan.schedule] == [1, 2, 3]


def test_rule_with_a_single_installment_offers_no_plan() -> None:
    assert build_offers(terms(installments=1), Decimal("1000"), TODAY).installments is None


@pytest.mark.parametrize(
    ("total", "count", "expected"),
    [
        ("100", 3, ["33.33", "33.33", "33.34"]),
        ("200", 3, ["66.66", "66.66", "66.68"]),
        ("90", 3, ["30.00", "30.00", "30.00"]),
    ],
)
def test_installments_always_add_up_to_the_exact_total(
    total: str, count: int, expected: list[str]
) -> None:
    parts = split_in_installments(Decimal(total), count)
    assert parts == [Decimal(x) for x in expected]
    assert sum(parts) == Decimal(total)


def test_percentages_round_half_up_to_cents() -> None:
    # 10 % de 1234,45 = 123,445 -> 123,45
    offer = build_offers(terms(discount="10"), Decimal("1234.45"), TODAY).single_payment
    assert offer.discount_amount == Decimal("123.45")
    assert offer.total_amount == Decimal("1111.00")


def test_add_months_handles_short_months() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
