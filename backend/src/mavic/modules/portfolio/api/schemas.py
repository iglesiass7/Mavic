"""Contratos de la API de cartera.

Los montos viajan como TEXTO en el JSON ("120000.00"), no como número. Un
número JSON lo leen JavaScript y muchos lenguajes como float, y se pierden
centavos. El frontend recibe el texto exacto y lo formatea para mostrar.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from mavic.modules.portfolio.application.cases import (
    CaseDetailView,
    CaseSummaryView,
    DebtorView,
    GenerationResult,
    InvoiceView,
)
from mavic.modules.portfolio.application.imports import ImportReport, ImportView
from mavic.modules.portfolio.domain.cases import CaseStatus, InvoiceStage


class RowErrorOut(BaseModel):
    row: int
    column: str | None
    code: str
    message: str


class ImportReportOut(BaseModel):
    ok: bool
    total_rows: int
    debtors_created: int
    debtors_updated: int
    invoices_created: int
    invoices_updated: int
    invoices_unchanged: int
    errors: list[RowErrorOut]
    import_id: UUID | None

    @classmethod
    def from_report(cls, report: ImportReport) -> "ImportReportOut":
        return cls(
            ok=report.is_valid,
            total_rows=report.total_rows,
            debtors_created=report.debtors_created,
            debtors_updated=report.debtors_updated,
            invoices_created=report.invoices_created,
            invoices_updated=report.invoices_updated,
            invoices_unchanged=report.invoices_unchanged,
            errors=[
                RowErrorOut(row=e.row_number, column=e.column, code=e.code, message=e.message)
                for e in report.errors
            ],
            import_id=report.import_id,
        )


class ImportOut(BaseModel):
    id: UUID
    filename: str
    user_id: UUID
    total_rows: int
    invoices_created: int
    invoices_updated: int
    invoices_unchanged: int
    created_at: datetime

    @classmethod
    def from_view(cls, view: ImportView) -> "ImportOut":
        return cls(**view.__dict__)


class DebtorOut(BaseModel):
    id: UUID
    name: str
    document_number: str
    phone: str
    email: str

    @classmethod
    def from_view(cls, view: DebtorView) -> "DebtorOut":
        return cls(**view.__dict__)


class InvoiceOut(BaseModel):
    id: UUID
    external_id: str
    description: str
    amount: Decimal
    currency: str
    due_date: date
    stage: InvoiceStage
    debtor_id: UUID
    debtor_name: str
    case_id: UUID | None
    case_number: int | None

    @classmethod
    def from_view(cls, view: InvoiceView) -> "InvoiceOut":
        return cls(**view.__dict__)


class CaseSummaryOut(BaseModel):
    id: UUID
    number: int
    status: CaseStatus
    debtor: DebtorOut
    invoice_count: int
    total_amount: Decimal
    oldest_due_date: date
    debt_age_days: int

    @classmethod
    def from_view(cls, view: CaseSummaryView) -> "CaseSummaryOut":
        return cls(**{**view.__dict__, "debtor": DebtorOut.from_view(view.debtor)})


class CaseDetailOut(CaseSummaryOut):
    invoices: list[InvoiceOut]

    @classmethod
    def from_detail(cls, view: CaseDetailView) -> "CaseDetailOut":
        summary = CaseSummaryOut.from_view(view.summary)
        return cls(
            **summary.model_dump(exclude={"debtor"}),
            debtor=summary.debtor,
            invoices=[InvoiceOut.from_view(i) for i in view.invoices],
        )


class GenerationOut(BaseModel):
    cases_created: int
    cases_updated: int
    invoices_assigned: int

    @classmethod
    def from_result(cls, result: GenerationResult) -> "GenerationOut":
        return cls(**result.__dict__)
