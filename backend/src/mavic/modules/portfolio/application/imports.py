"""CU-04 · Importar facturas desde un archivo CSV o Excel.

Dos pasos, como en el original, pero con reglas más claras:

    1. preview_import  -> valida TODO y dice qué va a pasar. No escribe nada.
    2. import_invoices -> vuelve a validar y, si no hay errores, guarda todo
                          en UNA transacción. Si hay un solo error, no guarda nada.

¿Qué pasa con una factura que ya existe (mismo número en la misma empresa)?

    | Situación de la factura existente | Datos del archivo  | Resultado        |
    |-----------------------------------|--------------------|------------------|
    | sin caso                          | iguales o distintos| se actualiza     |
    | dentro de un caso                 | iguales            | sin cambios      |
    | dentro de un caso                 | distintos          | ERROR (bloquea)  |

La última fila es clave: una factura que ya está en un caso pudo haberse
negociado con el deudor. Cambiarle el monto en silencio rompería lo acordado.
En el original eso pasaba sin aviso.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import BusinessRuleViolationError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditAction, Subject
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.portfolio.domain.import_rows import (
    MAX_ERRORS,
    ImportRow,
    RowError,
    missing_columns,
    validate_rows,
)
from mavic.modules.portfolio.infrastructure.file_reader import read_table
from mavic.modules.portfolio.infrastructure.orm import (
    DebtorModel,
    InvoiceImportModel,
    InvoiceModel,
)
from mavic.modules.portfolio.infrastructure.repositories import (
    DebtorRepository,
    ImportRepository,
    InvoiceRepository,
    lock_company_portfolio,
)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass
class ImportReport:
    """Resultado de validar (y opcionalmente cargar) un archivo."""

    total_rows: int
    errors: list[RowError] = field(default_factory=list)
    debtors_created: int = 0
    debtors_updated: int = 0
    invoices_created: int = 0
    invoices_updated: int = 0
    invoices_unchanged: int = 0
    import_id: uuid.UUID | None = None  # solo si se cargó

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _read_and_validate(filename: str, content: bytes) -> tuple[list[ImportRow], ImportReport]:
    if len(content) > MAX_FILE_BYTES:
        raise BusinessRuleViolationError(
            "El archivo supera el máximo de 5 MB.", code="FILE_TOO_LARGE"
        )
    table = read_table(filename, content)
    missing = missing_columns(table.headers)
    if missing:
        raise BusinessRuleViolationError(
            f"Faltan columnas obligatorias: {', '.join(missing)}.", code="MISSING_COLUMNS"
        )
    result = validate_rows(table.rows)
    return result.rows, ImportReport(total_rows=result.total_rows, errors=list(result.errors))


def _invoice_matches(invoice: InvoiceModel, row: ImportRow, debtor_id: uuid.UUID | None) -> bool:
    return (
        invoice.debtor_id == debtor_id
        and invoice.description == row.description
        and invoice.amount == row.amount
        and invoice.currency == row.currency
        and invoice.due_date == row.due_date
    )


def _plan_and_apply(
    session: Session,
    company_id: uuid.UUID,
    rows: list[ImportRow],
    report: ImportReport,
    *,
    apply: bool,
) -> None:
    """Compara el archivo contra la base. Si `apply` es True, además escribe.

    La misma función sirve para la vista previa y para la carga real: así la
    vista previa nunca promete algo distinto de lo que después pasa.
    """
    debtors = DebtorRepository(session)
    invoices = InvoiceRepository(session)
    existing_debtors = debtors.by_documents(company_id, {r.debtor_document for r in rows})
    existing_invoices = invoices.by_external_ids(company_id, {r.external_id for r in rows})

    # 1) Deudores: uno por documento (el archivo ya garantizó que sus datos coinciden).
    debtor_by_document: dict[str, DebtorModel] = {}
    for row in rows:
        if row.debtor_document in debtor_by_document:
            continue
        debtor = existing_debtors.get(row.debtor_document)
        if debtor is None:
            report.debtors_created += 1
            debtor = DebtorModel(
                company_id=company_id,
                document_number=row.debtor_document,
                name=row.debtor_name,
                phone=row.debtor_phone,
                email=row.debtor_email,
            )
            if apply:
                debtors.add(debtor)
        elif (debtor.name, debtor.phone, debtor.email) != row.debtor_key():
            report.debtors_updated += 1
            if apply:
                debtor.name, debtor.phone, debtor.email = row.debtor_key()
        debtor_by_document[row.debtor_document] = debtor

    if apply:
        session.flush()  # los deudores nuevos reciben su id antes de crear las facturas

    # 2) Facturas.
    for row in rows:
        debtor = debtor_by_document[row.debtor_document]
        invoice = existing_invoices.get(row.external_id)
        if invoice is None:
            report.invoices_created += 1
            if apply:
                invoices.add(
                    InvoiceModel(
                        company_id=company_id,
                        debtor_id=debtor.id,
                        external_id=row.external_id,
                        description=row.description,
                        amount=row.amount,
                        currency=row.currency,
                        due_date=row.due_date,
                    )
                )
        elif _invoice_matches(invoice, row, debtor.id):
            report.invoices_unchanged += 1
        elif invoice.case_id is not None:
            if len(report.errors) < MAX_ERRORS:
                report.errors.append(
                    RowError(
                        row.row_number,
                        "external_id",
                        "INVOICE_IN_CASE",
                        f"La factura '{row.external_id}' ya está en un caso y sus datos "
                        "cambiaron. No se modifica una factura que puede estar en negociación.",
                    )
                )
        else:
            report.invoices_updated += 1
            if apply:
                invoice.debtor_id = debtor.id
                invoice.description = row.description
                invoice.amount = row.amount
                invoice.currency = row.currency
                invoice.due_date = row.due_date


def preview_import(
    session: Session, *, actor: Actor, filename: str, content: bytes
) -> ImportReport:
    """Valida el archivo y cuenta qué se crearía o actualizaría. No escribe nada."""
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()
    rows, report = _read_and_validate(filename, content)
    _plan_and_apply(session, company_id, rows, report, apply=False)
    return report


def import_invoices(
    session: Session, *, actor: Actor, filename: str, content: bytes, clock: Clock
) -> ImportReport:
    """Carga el archivo en una sola transacción: todo o nada."""
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()
    rows, report = _read_and_validate(filename, content)
    if not report.is_valid:
        return report  # con errores de formato no se toca la base

    # Un solo proceso a la vez modifica la cartera de esta empresa (ver repositorio).
    lock_company_portfolio(session, company_id)
    _plan_and_apply(session, company_id, rows, report, apply=True)
    if not report.is_valid:
        session.rollback()  # apareció un conflicto con la base: se descarta todo
        return report

    record = InvoiceImportModel(
        company_id=company_id,
        user_id=actor.user_id,
        filename=filename[:255],
        total_rows=report.total_rows,
        debtors_created=report.debtors_created,
        debtors_updated=report.debtors_updated,
        invoices_created=report.invoices_created,
        invoices_updated=report.invoices_updated,
        invoices_unchanged=report.invoices_unchanged,
        created_at=clock.now(),
    )
    ImportRepository(session).add(record)
    session.flush()
    audit.record(
        session,
        company_id=company_id,
        actor=actor,
        action=AuditAction.INVOICES_IMPORTED,
        subject=Subject("import", str(record.id), record.filename),
        summary=f"Cargó {record.filename}: {report.invoices_created} facturas nuevas, "
        f"{report.invoices_updated} actualizadas y {report.invoices_unchanged} sin cambios.",
        details={
            "filas": report.total_rows,
            "deudores_nuevos": report.debtors_created,
            "deudores_actualizados": report.debtors_updated,
        },
    )
    session.commit()
    report.import_id = record.id
    return report


@dataclass(frozen=True)
class ImportView:
    id: uuid.UUID
    filename: str
    user_id: uuid.UUID
    total_rows: int
    invoices_created: int
    invoices_updated: int
    invoices_unchanged: int
    created_at: datetime


def recent_imports(session: Session, *, actor: Actor) -> list[ImportView]:
    """Historial de cargas de la empresa: quién subió qué y cuándo."""
    actor.require(Permission.VIEW_PORTFOLIO)
    return [
        ImportView(
            id=record.id,
            filename=record.filename,
            user_id=record.user_id,
            total_rows=record.total_rows,
            invoices_created=record.invoices_created,
            invoices_updated=record.invoices_updated,
            invoices_unchanged=record.invoices_unchanged,
            created_at=record.created_at,
        )
        for record in ImportRepository(session).recent(actor.require_company())
    ]
