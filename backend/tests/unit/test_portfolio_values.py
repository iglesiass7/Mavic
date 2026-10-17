from datetime import date, datetime
from decimal import Decimal

import pytest

from mavic.modules.portfolio.domain import values
from mavic.modules.portfolio.domain.values import InvalidValueError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.56", Decimal("1234.56")),
        ("1234,56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("$ 18.500", Decimal("18.50")),  # sin coma, el punto es decimal
        ("18.500,00", Decimal("18500.00")),
        (120000, Decimal("120000.00")),
        (1234.5600000000002, Decimal("1234.56")),  # ruido de float de Excel
    ],
)
def test_amounts_in_local_and_excel_formats(raw: object, expected: Decimal) -> None:
    assert values.parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-10", "abc", "12.345", "", None, True, "1e400"])
def test_invalid_amounts(raw: object) -> None:
    with pytest.raises(InvalidValueError):
        values.parse_amount(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("20.123.456", "20123456"), ("20-12345678-9", "20123456789"), (20123456.0, "20123456")],
)
def test_documents_keep_only_digits(raw: object, expected: str) -> None:
    assert values.parse_document(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "123456789012", "DNI 30111222", ""])
def test_invalid_documents(raw: object) -> None:
    with pytest.raises(InvalidValueError) as error:
        values.parse_document(raw)
    assert error.value.code in {"INVALID_DOCUMENT", "REQUIRED"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+54 9 11 5555-0101", "+5491155550101"),
        ("011 15 5555-0101", "+5491155550101"),  # formato local de celular
        ("11 5555-0103", "+541155550103"),
        ("+1 650 253 0000", "+16502530000"),  # números de otros países también
    ],
)
def test_phones_are_normalized_to_e164(raw: str, expected: str) -> None:
    assert values.parse_phone(raw) == expected


@pytest.mark.parametrize("raw", ["5555-0101", "abc", "+54 9"])
def test_invalid_phones(raw: str) -> None:
    with pytest.raises(InvalidValueError) as error:
        values.parse_phone(raw)
    assert error.value.code == "INVALID_PHONE"


def test_email_is_normalized_to_lowercase() -> None:
    assert values.parse_email(" Ana.Torres@Example.COM ") == "ana.torres@example.com"


def test_invalid_email() -> None:
    with pytest.raises(InvalidValueError):
        values.parse_email("ana@")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-10", date(2026, 9, 10)),
        ("10/09/2026", date(2026, 9, 10)),  # día/mes/año, como se escribe en Argentina
        (datetime(2026, 9, 10, 0, 0), date(2026, 9, 10)),  # celda de fecha de Excel
    ],
)
def test_due_dates(raw: object, expected: date) -> None:
    assert values.parse_due_date(raw) == expected


@pytest.mark.parametrize("raw", ["09/31/2026", "2026/09/10", "mañana"])
def test_invalid_due_dates(raw: str) -> None:
    with pytest.raises(InvalidValueError):
        values.parse_due_date(raw)


def test_only_ars_is_supported_for_now() -> None:
    assert values.parse_currency("ars") == "ARS"
    with pytest.raises(InvalidValueError) as error:
        values.parse_currency("USD")
    assert error.value.code == "UNSUPPORTED_CURRENCY"
