"""Validación de un archivo de facturas, fila por fila.

Recibe las filas ya leídas del archivo (diccionarios columna -> valor) y
devuelve dos listas: las filas válidas, ya normalizadas, y los errores
encontrados, con número de fila y columna para que la persona los corrija.

Además de validar cada fila por separado, revisa reglas ENTRE filas:
- el mismo número de factura no puede aparecer dos veces en el archivo;
- un mismo documento no puede venir con datos de deudor distintos
  (¿cuál de los dos teléfonos es el bueno? Mejor preguntar que adivinar).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from mavic.modules.portfolio.domain import values
from mavic.modules.portfolio.domain.values import InvalidValueError

# Columnas obligatorias del archivo (mismo formato que la plantilla original de Rynx).
REQUIRED_COLUMNS = (
    "external_id",
    "description",
    "debtor_name",
    "debtor_document",
    "debtor_phone",
    "debtor_email",
    "amount",
    "currency",
    "due_date",
)
MAX_ERRORS = 200  # tope de errores que se devuelven: con 200 ya hay bastante para corregir


@dataclass(frozen=True)
class ImportRow:
    """Una fila válida y normalizada."""

    row_number: int  # número de fila en la planilla (la 1 es el encabezado)
    external_id: str
    description: str
    debtor_name: str
    debtor_document: str
    debtor_phone: str
    debtor_email: str
    amount: Decimal
    currency: str
    due_date: date

    def debtor_key(self) -> tuple[str, str, str]:
        return (self.debtor_name, self.debtor_phone, self.debtor_email)


@dataclass(frozen=True)
class RowError:
    row_number: int
    column: str | None  # None: el error no es de una columna puntual
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    rows: list[ImportRow]
    errors: list[RowError]
    total_rows: int

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _text(max_length: int) -> Callable[[object], str]:
    return lambda raw: values.clean_text(raw, max_length=max_length)


def missing_columns(headers: Sequence[str]) -> list[str]:
    present = set(headers)
    return [column for column in REQUIRED_COLUMNS if column not in present]


def _parse[T](
    raw: Mapping[str, object],
    column: str,
    parser: Callable[[object], T],
    row_number: int,
    errors: list[RowError],
) -> T | None:
    """Valida una celda. Si falla, anota el error y devuelve None."""
    try:
        return parser(raw.get(column))
    except InvalidValueError as error:
        errors.append(RowError(row_number, column, error.code, error.message))
        return None


def _validate_row(row_number: int, raw: Mapping[str, object]) -> ImportRow | list[RowError]:
    errors: list[RowError] = []
    external_id = _parse(raw, "external_id", _text(100), row_number, errors)
    description = _parse(raw, "description", _text(255), row_number, errors)
    debtor_name = _parse(raw, "debtor_name", _text(120), row_number, errors)
    document = _parse(raw, "debtor_document", values.parse_document, row_number, errors)
    phone = _parse(raw, "debtor_phone", values.parse_phone, row_number, errors)
    email = _parse(raw, "debtor_email", values.parse_email, row_number, errors)
    amount = _parse(raw, "amount", values.parse_amount, row_number, errors)
    currency = _parse(raw, "currency", values.parse_currency, row_number, errors)
    due_date = _parse(raw, "due_date", values.parse_due_date, row_number, errors)

    if (
        errors
        or external_id is None
        or description is None
        or debtor_name is None
        or document is None
        or phone is None
        or email is None
        or amount is None
        or currency is None
        or due_date is None
    ):
        return errors
    return ImportRow(
        row_number=row_number,
        external_id=external_id,
        description=description,
        debtor_name=debtor_name,
        debtor_document=document,
        debtor_phone=phone,
        debtor_email=email,
        amount=amount,
        currency=currency,
        due_date=due_date,
    )


def validate_rows(raw_rows: Sequence[tuple[int, Mapping[str, object]]]) -> ValidationResult:
    """Valida todas las filas. `raw_rows` = [(número de fila, {columna: valor}), ...]."""
    rows: list[ImportRow] = []
    errors: list[RowError] = []
    first_row_of_invoice: dict[str, int] = {}
    debtor_data: dict[str, tuple[int, tuple[str, str, str]]] = {}

    for row_number, raw in raw_rows:
        result = _validate_row(row_number, raw)
        if isinstance(result, list):
            errors.extend(result)
            continue

        if result.external_id in first_row_of_invoice:
            errors.append(
                RowError(
                    row_number,
                    "external_id",
                    "DUPLICATED_IN_FILE",
                    f"La factura '{result.external_id}' ya aparece en la fila "
                    f"{first_row_of_invoice[result.external_id]}.",
                )
            )
            continue
        first_row_of_invoice[result.external_id] = row_number

        previous = debtor_data.get(result.debtor_document)
        if previous is not None and previous[1] != result.debtor_key():
            errors.append(
                RowError(
                    row_number,
                    "debtor_document",
                    "INCONSISTENT_DEBTOR",
                    f"El documento {result.debtor_document} tiene nombre, teléfono o email "
                    f"distintos a los de la fila {previous[0]}.",
                )
            )
            continue
        debtor_data.setdefault(result.debtor_document, (row_number, result.debtor_key()))
        rows.append(result)

    return ValidationResult(rows=rows, errors=errors[:MAX_ERRORS], total_rows=len(raw_rows))
