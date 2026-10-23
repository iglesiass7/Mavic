"""Consultas de la cartera. Todas reciben `company_id`: no hay forma de pedir
datos "de todas las empresas" desde acá.

Recordatorio de la regla del proyecto: los repositorios no hacen commit.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import ColumnElement, Select, Subquery, func, or_, select, text
from sqlalchemy.orm import Session

from mavic.modules.portfolio.domain.cases import CaseStatus, InvoiceStage
from mavic.modules.portfolio.infrastructure.orm import (
    CaseModel,
    DebtorModel,
    InvoiceImportModel,
    InvoiceModel,
)

CaseSort = Literal[
    "oldest_debt",
    "highest_amount",
    "newest",
    "number",
    "-number",
    "debtor",
    "-debtor",
    "document",
    "-document",
    "amount",
    "-amount",
    "invoices",
    "-invoices",
    "status",
    "-status",
]


@dataclass(frozen=True)
class CaseFilters:
    status: CaseStatus | None = None
    search: str | None = None  # nombre, DNI o número de caso
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


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
class UnassignedTotals:
    overdue_count: int
    overdue_amount: Decimal
    upcoming_count: int
    upcoming_amount: Decimal


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

    def unassigned_totals(self, company_id: uuid.UUID, today: date) -> "UnassignedTotals":
        """Facturas que todavía no están en un caso: vencidas y por vencer.

        "Vencida" usa la misma condición que unassigned_overdue (vence ANTES de
        hoy): son exactamente las que agruparía "Generar casos".
        """
        overdue = InvoiceModel.due_date < today
        row = self._session.execute(
            select(
                func.count().filter(overdue),
                func.coalesce(func.sum(InvoiceModel.amount).filter(overdue), 0),
                func.count().filter(~overdue),
                func.coalesce(func.sum(InvoiceModel.amount).filter(~overdue), 0),
            ).where(InvoiceModel.company_id == company_id, InvoiceModel.case_id.is_(None))
        ).one()
        return UnassignedTotals(int(row[0]), Decimal(row[1]), int(row[2]), Decimal(row[3]))

    def due_between_with_debtor(
        self, company_id: uuid.UUID, first: date, last: date
    ) -> list[tuple[InvoiceModel, DebtorModel]]:
        """Facturas sin caso que vencen entre `first` y `last` (incluidos), con su deudor."""
        query = (
            select(InvoiceModel, DebtorModel)
            .join(DebtorModel, DebtorModel.id == InvoiceModel.debtor_id)
            .where(
                InvoiceModel.company_id == company_id,
                InvoiceModel.case_id.is_(None),
                InvoiceModel.due_date >= first,
                InvoiceModel.due_date <= last,
            )
            .order_by(InvoiceModel.due_date, InvoiceModel.external_id)
        )
        return [(invoice, debtor) for invoice, debtor in self._session.execute(query)]

    def of_case(self, case_id: uuid.UUID) -> list[InvoiceModel]:
        query = (
            select(InvoiceModel)
            .where(InvoiceModel.case_id == case_id)
            .order_by(InvoiceModel.due_date, InvoiceModel.external_id)
        )
        return list(self._session.scalars(query))

    def _filtered(
        self, company_id: uuid.UUID, filters: "InvoiceFilters"
    ) -> Select[InvoiceModel, str, int]:
        """Las facturas de la empresa con todos los filtros MENOS el rango de monto."""
        query = (
            select(InvoiceModel, DebtorModel.name, CaseModel.number)
            .join(DebtorModel, DebtorModel.id == InvoiceModel.debtor_id)
            .outerjoin(CaseModel, CaseModel.id == InvoiceModel.case_id)
            .where(InvoiceModel.company_id == company_id)
        )
        if filters.in_case is True:
            query = query.where(InvoiceModel.case_id.is_not(None))
        elif filters.in_case is False:
            query = query.where(InvoiceModel.case_id.is_(None))
        if filters.overdue_before is not None:
            query = query.where(InvoiceModel.due_date < filters.overdue_before)
        if filters.stage is not None:
            today = filters.today
            query = query.where(
                {
                    InvoiceStage.UPCOMING: InvoiceModel.due_date > today,
                    InvoiceStage.DUE_TODAY: InvoiceModel.due_date == today,
                    InvoiceStage.OVERDUE: InvoiceModel.due_date < today,
                }[filters.stage]
            )
        if filters.search:
            pattern = _like(filters.search)
            query = query.where(
                or_(
                    InvoiceModel.external_id.ilike(pattern, escape="\\"),
                    InvoiceModel.description.ilike(pattern, escape="\\"),
                    DebtorModel.name.ilike(pattern, escape="\\"),
                    DebtorModel.document_number.ilike(pattern, escape="\\"),
                )
            )
        return query

    def page(
        self,
        company_id: uuid.UUID,
        filters: "InvoiceFilters",
        *,
        sort: "InvoiceSort",
        limit: int,
        offset: int,
    ) -> tuple[list[InvoiceRow], int, Decimal]:
        """Una página, el total filtrado y el monto más alto (para el rango del filtro)."""
        base = self._filtered(company_id, filters)
        amount_max = self._session.scalar(select(func.max(base.subquery().c.amount))) or Decimal(0)
        query = base
        if filters.min_amount is not None:
            query = query.where(InvoiceModel.amount >= filters.min_amount)
        if filters.max_amount is not None:
            query = query.where(InvoiceModel.amount <= filters.max_amount)
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        column = {
            "due_date": InvoiceModel.due_date,
            "amount": InvoiceModel.amount,
            "external_id": InvoiceModel.external_id,
            "description": InvoiceModel.description,
            "debtor": DebtorModel.name,
        }[sort.lstrip("-")]
        order = column.desc() if sort.startswith("-") else column.asc()
        rows = self._session.execute(
            query.order_by(order, InvoiceModel.external_id).limit(limit).offset(offset)
        ).all()
        return [InvoiceRow(row[0], row[1], row[2]) for row in rows], total, Decimal(amount_max)


InvoiceSort = Literal[
    "due_date",
    "-due_date",
    "amount",
    "-amount",
    "external_id",
    "-external_id",
    "description",
    "-description",
    "debtor",
    "-debtor",
]


@dataclass(frozen=True)
class InvoiceFilters:
    """Filtros de la lista de facturas. `today` hace falta si se filtra por `stage`."""

    in_case: bool | None = None
    overdue_before: date | None = None
    stage: InvoiceStage | None = None
    today: date | None = None
    search: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


def _like(text: str) -> str:
    r"""Patrón para ILIKE que busca el texto TAL CUAL ("50%" no es un comodín).

    >>> _like("50%_a")
    '%50\\%\\_a%'
    """
    escaped = text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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

    def by_number(self, number: int) -> CaseModel | None:
        return self._session.scalar(select(CaseModel).where(CaseModel.number == number))

    def get_for_update(self, company_id: uuid.UUID, case_id: uuid.UUID) -> CaseModel | None:
        """El caso, bloqueado hasta el final de la transacción (SELECT ... FOR UPDATE)."""
        return self._session.scalar(
            select(CaseModel)
            .where(CaseModel.company_id == company_id, CaseModel.id == case_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def pending_by_debtor(
        self, company_id: uuid.UUID, debtor_ids: set[uuid.UUID]
    ) -> dict[tuple[uuid.UUID, str], CaseModel]:
        """Los casos pendientes de esos deudores, por (deudor, moneda)."""
        if not debtor_ids:
            return {}
        query = select(CaseModel).where(
            CaseModel.company_id == company_id,
            CaseModel.debtor_id.in_(debtor_ids),
            CaseModel.status == CaseStatus.PENDING,
        )
        return {(case.debtor_id, case.currency): case for case in self._session.scalars(query)}

    @staticmethod
    def _case_totals(company_id: uuid.UUID) -> Subquery:
        """Por caso: cantidad de facturas, total y vencimiento más viejo."""
        return (
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

    def totals_by_status(self, company_id: uuid.UUID) -> list[tuple[CaseStatus, int, Decimal]]:
        """Cuántos casos hay en cada estado y cuánto suman sus facturas."""
        totals = self._case_totals(company_id)
        rows = self._session.execute(
            select(CaseModel.status, func.count(), func.sum(totals.c.total_amount))
            .join(totals, totals.c.case_id == CaseModel.id)
            .where(CaseModel.company_id == company_id)
            .group_by(CaseModel.status)
        ).all()
        return [(CaseStatus(r[0]), int(r[1]), Decimal(r[2])) for r in rows]

    def debts_in_status(
        self, company_id: uuid.UUID, statuses: frozenset[CaseStatus]
    ) -> list[tuple[date, Decimal]]:
        """Vencimiento más viejo y total de cada caso en esos estados (tramos de atraso)."""
        totals = self._case_totals(company_id)
        rows = self._session.execute(
            select(totals.c.oldest_due_date, totals.c.total_amount)
            .join(CaseModel, CaseModel.id == totals.c.case_id)
            .where(CaseModel.company_id == company_id, CaseModel.status.in_(statuses))
        ).all()
        return [(r[0], Decimal(r[1])) for r in rows]

    def _summaries(
        self, company_id: uuid.UUID
    ) -> Select[CaseModel, DebtorModel, int, Decimal, date]:
        """Cada caso con su deudor y los totales de sus facturas, en UNA consulta."""
        totals = self._case_totals(company_id)
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
        filters: "CaseFilters",
        *,
        sort: "CaseSort",
        limit: int,
        offset: int,
    ) -> tuple[list[CaseRow], int, Decimal]:
        """Una página, el total filtrado y la deuda más alta (para el rango del filtro)."""
        query = self._summaries(company_id)
        amount = query.selected_columns.total_amount
        if filters.status is not None:
            query = query.where(CaseModel.status == filters.status)
        if filters.search:
            pattern = _like(filters.search)
            matches: list[ColumnElement[bool]] = [
                DebtorModel.name.ilike(pattern, escape="\\"),
                DebtorModel.document_number.ilike(pattern, escape="\\"),
            ]
            digits = filters.search.strip().lstrip("#")
            if digits.isdigit() and len(digits) <= 18:
                matches.append(CaseModel.number == int(digits))
            query = query.where(or_(*matches))
        amount_max = self._session.scalar(
            select(func.max(query.subquery().c.total_amount))
        ) or Decimal(0)
        if filters.min_amount is not None:
            query = query.where(amount >= filters.min_amount)
        if filters.max_amount is not None:
            query = query.where(amount <= filters.max_amount)
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0

        columns = query.selected_columns
        order = {
            "oldest_debt": (columns.oldest_due_date.asc(), CaseModel.number),
            "highest_amount": (columns.total_amount.desc(), CaseModel.number),
            "newest": (CaseModel.number.desc(),),
            "number": (CaseModel.number.asc(),),
            "-number": (CaseModel.number.desc(),),
            "debtor": (DebtorModel.name.asc(), CaseModel.number),
            "-debtor": (DebtorModel.name.desc(), CaseModel.number),
            "document": (DebtorModel.document_number.asc(), CaseModel.number),
            "-document": (DebtorModel.document_number.desc(), CaseModel.number),
            "amount": (columns.total_amount.asc(), CaseModel.number),
            "-amount": (columns.total_amount.desc(), CaseModel.number),
            "invoices": (columns.invoice_count.asc(), CaseModel.number),
            "-invoices": (columns.invoice_count.desc(), CaseModel.number),
            "status": (CaseModel.status.asc(), CaseModel.number),
            "-status": (CaseModel.status.desc(), CaseModel.number),
        }[sort]
        rows = self._session.execute(query.order_by(*order).limit(limit).offset(offset)).all()
        return [self._to_row(*row) for row in rows], total, Decimal(amount_max)

    def with_debtor_names(
        self, company_id: uuid.UUID, case_ids: set[uuid.UUID]
    ) -> list[tuple[CaseModel, str]]:
        if not case_ids:
            return []
        rows = self._session.execute(
            select(CaseModel, DebtorModel.name)
            .join(DebtorModel, DebtorModel.id == CaseModel.debtor_id)
            .where(CaseModel.company_id == company_id, CaseModel.id.in_(case_ids))
        ).all()
        return [(row[0], row[1]) for row in rows]

    def ids_matching(self, company_id: uuid.UUID, search: str) -> set[uuid.UUID]:
        pattern = _like(search)
        matches: list[ColumnElement[bool]] = [
            DebtorModel.name.ilike(pattern, escape="\\"),
            DebtorModel.document_number.ilike(pattern, escape="\\"),
        ]
        digits = search.strip().lstrip("#")
        if digits.isdigit() and len(digits) <= 18:
            matches.append(CaseModel.number == int(digits))
        return set(
            self._session.scalars(
                select(CaseModel.id)
                .join(DebtorModel, DebtorModel.id == CaseModel.debtor_id)
                .where(CaseModel.company_id == company_id, or_(*matches))
            )
        )

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
