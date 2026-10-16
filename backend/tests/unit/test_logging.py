import json
import logging

from mavic.core.logging import JsonFormatter, PersonalDataFilter, redact, request_id_var


def test_redact_masks_email_keeping_first_letter_and_domain() -> None:
    assert redact("contacto: ana.perez@mail.com") == "contacto: a***@mail.com"


def test_redact_masks_document_and_phone_numbers() -> None:
    text = redact("DNI 30111222, tel +5491122334455")
    assert "30111222" not in text
    assert "5491122334455" not in text
    assert text.count("[número oculto]") == 2


def test_redact_keeps_short_numbers_like_ids_and_amounts() -> None:
    assert redact("caso 42 por $120000") == "caso 42 por $120000"


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, message, args, None)


def test_filter_masks_values_passed_as_log_arguments() -> None:
    record = _record("deudor %s", "juan@mail.com")
    PersonalDataFilter().filter(record)
    assert record.getMessage() == "deudor j***@mail.com"


def test_json_formatter_includes_request_id_and_extra_fields() -> None:
    token = request_id_var.set("abc123def")
    try:
        record = _record("GET /health -> 200")
        record.status_code = 200
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert line["request_id"] == "abc123def"
    assert line["message"] == "GET /health -> 200"
    assert line["status_code"] == 200
    assert line["level"] == "INFO"
