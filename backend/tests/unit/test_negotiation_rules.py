from decimal import Decimal

import pytest

from mavic.core.errors import BusinessRuleViolationError
from mavic.modules.negotiation.domain.rules import (
    CaseFacts,
    Interval,
    PaymentTerms,
    RuleConditions,
    applies_to,
    conditions_overlap,
    validate_conditions,
    validate_terms,
)


def conditions(
    amount: tuple[str, str | None] = ("0", "500000"),
    age: tuple[int, int | None] = (15, 59),
    invoices: tuple[int, int | None] = (1, 12),
) -> RuleConditions:
    return RuleConditions(
        amount=Interval(Decimal(amount[0]), Decimal(amount[1]) if amount[1] else None),
        debt_age_days=Interval(*age),
        invoice_count=Interval(*invoices),
    )


def terms(**overrides: object) -> PaymentTerms:
    values: dict[str, object] = {
        "discount_pct": Decimal("10"),
        "payment_days": 5,
        "max_installments": 3,
        "interest_pct": Decimal("8"),
    }
    values.update(overrides)
    return PaymentTerms(**values)  # type: ignore[arg-type]


def facts(amount: str = "100000", age: int = 30, invoices: int = 2) -> CaseFacts:
    return CaseFacts(total_amount=Decimal(amount), debt_age_days=age, invoice_count=invoices)


# ---------------------------------------------------------------- rangos


def test_interval_includes_both_ends() -> None:
    interval = Interval(15, 59)
    assert interval.contains(15)
    assert interval.contains(59)
    assert not interval.contains(14)
    assert not interval.contains(60)


def test_interval_without_maximum_has_no_limit() -> None:
    assert Interval(60, None).contains(10_000)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (Interval(0, 14), Interval(15, 59), False),  # se tocan pero no se pisan
        (Interval(0, 15), Interval(15, 59), True),  # comparten el 15
        (Interval(60, None), Interval(15, 59), False),
        (Interval(60, None), Interval(100, 200), True),
        (Interval(0, None), Interval(5, None), True),
    ],
)
def test_interval_overlap(a: Interval[int], b: Interval[int], expected: bool) -> None:
    assert a.overlaps(b) is expected
    assert b.overlaps(a) is expected  # da lo mismo en qué orden se comparan


# ---------------------------------------------------------------- elección de regla


def test_rule_applies_only_when_all_three_conditions_match() -> None:
    rule = conditions()
    assert applies_to(rule, facts())
    assert not applies_to(rule, facts(amount="500000.01"))
    assert not applies_to(rule, facts(age=60))
    assert not applies_to(rule, facts(invoices=13))


def test_rules_overlap_only_if_all_three_ranges_overlap() -> None:
    reciente = conditions(age=(0, 14))
    corto_plazo = conditions(age=(15, 59))
    deuda_alta = conditions(amount=("500000.01", None), age=(15, None), invoices=(1, None))

    assert not conditions_overlap(reciente, corto_plazo)  # distinto atraso
    assert not conditions_overlap(corto_plazo, deuda_alta)  # distinto monto
    assert conditions_overlap(corto_plazo, conditions(age=(30, 90)))


# ---------------------------------------------------------------- validación


def _code(action: object) -> str:
    with pytest.raises(BusinessRuleViolationError) as error:
        action()  # type: ignore[operator]
    return error.value.code


def test_valid_rule_passes() -> None:
    validate_conditions(conditions())
    validate_terms(terms())


def test_maximum_below_minimum_is_rejected() -> None:
    code = _code(lambda: validate_conditions(conditions(age=(60, 30))))
    assert code == "INVALID_RANGE"


def test_a_case_has_at_least_one_invoice() -> None:
    assert _code(lambda: validate_conditions(conditions(invoices=(0, 5)))) == "INVALID_RANGE"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"discount_pct": Decimal("100")}, "INVALID_DISCOUNT"),
        ({"discount_pct": Decimal("-1")}, "INVALID_DISCOUNT"),
        ({"interest_pct": Decimal("100.01")}, "INVALID_INTEREST"),
        ({"max_installments": 0}, "INVALID_INSTALLMENTS"),
        ({"max_installments": 37}, "INVALID_INSTALLMENTS"),
        ({"payment_days": 0}, "INVALID_PAYMENT_DAYS"),
    ],
)
def test_invalid_terms(overrides: dict[str, object], code: str) -> None:
    assert _code(lambda: validate_terms(terms(**overrides))) == code
