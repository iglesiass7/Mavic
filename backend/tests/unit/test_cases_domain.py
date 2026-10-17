from datetime import date

from mavic.modules.portfolio.domain.cases import InvoiceStage, debt_age_days, invoice_stage

TODAY = date(2026, 10, 16)


def test_invoice_stage() -> None:
    assert invoice_stage(date(2026, 10, 17), TODAY) == InvoiceStage.UPCOMING
    assert invoice_stage(TODAY, TODAY) == InvoiceStage.DUE_TODAY
    assert invoice_stage(date(2026, 10, 15), TODAY) == InvoiceStage.OVERDUE


def test_debt_age_counts_from_the_oldest_due_date() -> None:
    assert debt_age_days(date(2026, 9, 16), TODAY) == 30


def test_debt_age_is_never_negative() -> None:
    assert debt_age_days(date(2026, 12, 1), TODAY) == 0
