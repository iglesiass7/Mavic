"""Consultas de la cartera. Todas reciben `company_id`: no hay forma de pedir
datos "de todas las empresas" desde acá.

Recordatorio de la regla del proyecto: los repositorios no hacen commit.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.portfolio.infrastructure.orm import (
    CaseModel,
    DebtorModel,
    InvoiceImportModel,
    InvoiceModel,
)

CaseSort = Literal["oldest_debt", "highest_amount", "newest"]

# Espacio de nombres del bloqueo consultivo de la cartera (ver lock_company_portfolio).
_PORTFOLIO_LOCK_NAMESPACE = 1001


def lock_company_portfolio(session: Session, company_id: uuid.UUID) -> None:
    """Bloqueo "consultivo" (advisory lock) de PostgreSQL por empresa.

    Problema: si dos personas de la misma empresa importan un archivo, o
    importan y generan casos AL MISMO TIEMPO, las dos podrían crear el mismo
    deudor o dos casos pendientes para el mismo deudor.

    Solución: antes de modificar la cartera, el caso de uso pide este bloqueo.
    El segundo request espera a que el primero termine (commit o rollback) y
    recién ahí sigue, ya viendo los cambios del primero. Se libera solo al
    terminar la transacción ("xact"). Empresas distintas no se bloquean entre sí.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:company_id))"),
        {"namespace": _PORTFOLIO_LOCK_NAMESPACE, "company_id": str(company_id)},
    )


class DebtorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, debtor: DebtorModel) -> None:
        self._session.add(debtor)

    def by_documents(self, company_id: uuid.UUID, documents: set[str]) -> dict[str, DebtorModel]:
        if not documents:
            return {}
        query = select(DebtorModel).where(
            DebtorModel.company_id == company_id, DebtorModel.document_number.in_(documents)
        )
        return {debtor.document_number: debtor for debtor in self._session.scalars(query)}

    def get(self, company_id: uuid.UUID, debtor_id: uuid.UUID) -> DebtorModel | None:
        query = select(DebtorModel).where(
            DebtorModel.company_id == company_id, DebtorModel.id == debtor_id
        )
        return self._session.scalar(query)


@dataclass(frozen=True)
class InvoiceRow:
    invoice: InvoiceModel
    debtor_name: str
    case_number: int | None


class InvoiceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, invoice: InvoiceModel) -> None:
        self._session.add(invoice)

    def by_external_ids(self, company_id: uuid.UUID, ids: set[str]) -> dict[str, InvoiceModel]:
        if not ids:
            return {}
        query = select(InvoiceModel).where(
            InvoiceModel.company_id == company_id, InvoiceModel.external_id.in_(ids)
        )
        return {invoice.external_id: invoice for invoice in self._session.scalars(query)}

    def unassigned_overdue(self, company_id: uuid.UUID, today: date) -> list[InvoiceModel]:
        query = (
            select(InvoiceModel)
            .where(
                InvoiceModel.company_id == company_id,
                InvoiceModel.case_id.is_(None),
                InvoiceModel.due_date < today,
            )
            .order_by(InvoiceModel.debtor_id, InvoiceModel.due_date)
        )
        return list(self._session.scalars(query))

    def of_case(self, case_id: uuid.UUID) -> list[InvoiceModel]:
        query = (
            select(InvoiceModel)
            .where(InvoiceModel.case_id == case_id)
            .order_by(InvoiceModel.due_date, InvoiceModel.external_id)
        )
        return list(self._session.scalars(query))

    def _filtered(
        self, company_id: uuid.UUID, *, in_case: bool | None, overdue_before: date | None
    ) -> Select[InvoiceModel, str, int]:
        query = (
            select(InvoiceModel, DebtorModel.name, CaseModel.number)
            .join(DebtorModel, DebtorModel.id == InvoiceModel.debtor_id)
            .outerjoin(CaseModel, CaseModel.id == InvoiceModel.case_id)
            .where(InvoiceModel.company_id == company_id)
        )
        if in_case is True:
            query = query.where(InvoiceModel.case_id.is_not(None))
        elif in_case is False:
            query = query.where(InvoiceModel.case_id.is_(None))
        if overdue_before is not None:
            query = query.where(InvoiceModel.due_date < overdue_before)
        return query

    def page(
        self,
        company_id: uuid.UUID,
        *,
        in_case: bool | None,
        overdue_before: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InvoiceRow], int]:
        query = self._filtered(company_id, in_case=in_case, overdue_before=overdue_before)
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.execute(
            query.order_by(InvoiceModel.due_date, InvoiceModel.external_id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [InvoiceRow(row[0], row[1], row[2]) for row in rows], total


@dataclass(frozen=True)
class CaseRow:
    case: CaseModel
    debtor: DebtorModel
    invoice_count: int
    total_amount: Decimal
    oldest_due_date: date


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_row(
        case: CaseModel, debtor: DebtorModel, count: int, total: Decimal, oldest: date
    ) -> CaseRow:
        return CaseRow(case, debtor, count, total, oldest)

    def add(self, case: CaseModel) -> None:
        self._session.add(case)

    def pending_by_debtor(
        self, company_id: uuid.UUID, debtor_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, CaseModel]:
        if not debtor_ids:
            return {}
        query = select(CaseModel).where(
            CaseModel.company_id == company_id,
            CaseModel.debtor_id.in_(debtor_ids),
            CaseModel.status == CaseStatus.PENDING,
        )
        return {case.debtor_id: case for case in self._session.scalars(query)}

    def _summaries(
        self, company_id: uuid.UUID
    ) -> Select[CaseModel, DebtorModel, int, Decimal, date]:
        """Cada caso con su deudor y los totales de sus facturas, en UNA consulta."""
        totals = (
            select(
                InvoiceModel.case_id,
                func.count().label("invoice_count"),
                func.sum(InvoiceModel.amount).label("total_amount"),
                func.min(InvoiceModel.due_date).label("oldest_due_date"),
            )
            .where(InvoiceModel.company_id == company_id, InvoiceModel.case_id.is_not(None))
            .group_by(InvoiceModel.case_id)
            .subquery()
        )
        return (
            select(
                CaseModel,
                DebtorModel,
                totals.c.invoice_count,
                totals.c.total_amount,
                totals.c.oldest_due_date,
            )
            .join(DebtorModel, DebtorModel.id == CaseModel.debtor_id)
            .join(totals, totals.c.case_id == CaseModel.id)
            .where(CaseModel.company_id == company_id)
        )

    def page(
        self,
        company_id: uuid.UUID,
        *,
        status: CaseStatus | None,
        sort: CaseSort,
        limit: int,
        offset: int,
    ) -> tuple[list[CaseRow], int]:
        query = self._summaries(company_id)
        if status is not None:
            query = query.where(CaseModel.status == status)
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0

        order = {
            "oldest_debt": (query.selected_columns.oldest_due_date.asc(), CaseModel.number),
            "highest_amount": (query.selected_columns.total_amount.desc(), CaseModel.number),
            "newest": (CaseModel.number.desc(),),
        }[sort]
        rows = self._session.execute(query.order_by(*order).limit(limit).offset(offset)).all()
        return [self._to_row(*row) for row in rows], total

    def summary(self, company_id: uuid.UUID, case_id: uuid.UUID) -> CaseRow | None:
        row = self._session.execute(
            self._summaries(company_id).where(CaseModel.id == case_id)
        ).first()
        return None if row is None else self._to_row(*row)


class ImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: InvoiceImportModel) -> None:
        self._session.add(record)

    def recent(self, company_id: uuid.UUID, limit: int = 20) -> list[InvoiceImportModel]:
        query = (
            select(InvoiceImportModel)
            .where(InvoiceImportModel.company_id == company_id)
            .order_by(InvoiceImportModel.created_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(query))
