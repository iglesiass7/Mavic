import io
import zipfile
from datetime import datetime

import pytest
from openpyxl import Workbook

from mavic.core.errors import BusinessRuleViolationError
from mavic.modules.portfolio.infrastructure import file_reader
from mavic.modules.portfolio.infrastructure.file_reader import read_table


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _code(filename: str, content: bytes) -> str:
    with pytest.raises(BusinessRuleViolationError) as error:
        read_table(filename, content)
    return error.value.code


def test_csv_with_semicolons_like_spanish_excel() -> None:
    table = read_table("f.csv", b"external_id;amount\nF-1;1.234,56\n")
    assert table.headers == ["external_id", "amount"]
    assert table.rows == [(2, {"external_id": "F-1", "amount": "1.234,56"})]


def test_csv_in_windows_encoding_keeps_accents() -> None:
    table = read_table("f.csv", "debtor_name\nJosé Núñez\n".encode("cp1252"))
    assert table.rows[0][1]["debtor_name"] == "José Núñez"


def test_headers_are_case_and_space_insensitive_and_empty_rows_are_skipped() -> None:
    table = read_table("f.csv", b" External_ID ,Amount\n\nF-1,10\n,\nF-2,20\n")
    assert [number for number, _ in table.rows] == [3, 5]  # números de fila reales
    assert table.rows[0][1] == {"external_id": "F-1", "amount": "10"}


def test_xlsx_keeps_numbers_and_dates_as_typed_values() -> None:
    content = _xlsx([["external_id", "amount", "due_date"], ["F-1", 1500.5, datetime(2026, 9, 10)]])
    row = read_table("f.xlsx", content).rows[0][1]
    assert row["amount"] == 1500.5
    assert row["due_date"] == datetime(2026, 9, 10)


def test_unsupported_extension() -> None:
    assert _code("facturas.xls", b"...") == "UNSUPPORTED_FILE_TYPE"


def test_empty_file() -> None:
    assert _code("f.csv", b"external_id,amount\n") == "EMPTY_FILE"


def test_broken_xlsx() -> None:
    assert _code("f.xlsx", b"esto no es un excel") == "UNREADABLE_FILE"


def test_too_many_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_reader, "MAX_ROWS", 3)
    content = b"external_id\n" + b"".join(f"F-{i}\n".encode() for i in range(4))
    assert _code("f.csv", content) == "TOO_MANY_ROWS"


def test_zip_bomb_is_rejected_before_opening_it() -> None:
    # 60 MB de ceros se comprimen a unos pocos KB: el archivo subido es chico,
    # pero descomprimido tiraría el servidor.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * (60 * 1024 * 1024))
    content = buffer.getvalue()
    assert len(content) < 1024 * 1024
    assert _code("bomba.xlsx", content) == "FILE_TOO_LARGE"
