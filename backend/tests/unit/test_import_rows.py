from mavic.modules.portfolio.domain.import_rows import missing_columns, validate_rows

GOOD = {
    "external_id": "F-1",
    "description": "Abono",
    "debtor_name": "Ana Pérez",
    "debtor_document": "30111222",
    "debtor_phone": "+5491155550101",
    "debtor_email": "ana@example.com",
    "amount": "1000",
    "currency": "ARS",
    "due_date": "2026-09-10",
}


def test_valid_rows_are_normalized() -> None:
    result = validate_rows([(2, GOOD)])
    assert result.is_valid
    assert result.rows[0].debtor_phone == "+5491155550101"
    assert str(result.rows[0].amount) == "1000.00"


def test_every_invalid_cell_is_reported_with_row_and_column() -> None:
    bad = {**GOOD, "amount": "-5", "debtor_email": "no-es-email", "due_date": ""}
    result = validate_rows([(7, bad)])

    assert not result.rows
    reported = {(e.row_number, e.column, e.code) for e in result.errors}
    assert reported == {
        (7, "amount", "INVALID_AMOUNT"),
        (7, "debtor_email", "INVALID_EMAIL"),
        (7, "due_date", "REQUIRED"),
    }


def test_duplicated_invoice_in_the_same_file() -> None:
    result = validate_rows([(2, GOOD), (3, GOOD)])
    assert len(result.rows) == 1
    assert result.errors[0].code == "DUPLICATED_IN_FILE"
    assert "fila 2" in result.errors[0].message


def test_same_document_with_different_phone_is_rejected() -> None:
    other = {**GOOD, "external_id": "F-2", "debtor_phone": "+5491155550199"}
    result = validate_rows([(2, GOOD), (3, other)])
    assert result.errors[0].code == "INCONSISTENT_DEBTOR"
    assert result.errors[0].row_number == 3


def test_missing_columns_are_listed() -> None:
    assert missing_columns(["external_id", "amount"]) == [
        "description",
        "debtor_name",
        "debtor_document",
        "debtor_phone",
        "debtor_email",
        "currency",
        "due_date",
    ]
