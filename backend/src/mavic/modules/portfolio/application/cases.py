"""CU-05 · Agrupar facturas vencidas en casos, y consultar casos y facturas.

Regla para generar casos (en el original lo hacía el NAVEGADOR, con una llamada
HTTP por factura y sin transacción):

    Por cada deudor con facturas vencidas que todavía no están en un caso:
      - si ya tiene un caso PENDIENTE (todavía no contactado) -> se suman ahí;
      - si no                                                -> se crea un caso nuevo.

Un caso que ya fue contactado o negociado NO recibe facturas nuevas: lo que se
habló con el deudor fue sobre las facturas que tenía en ese momento.

La operación es idempotente: correrla dos veces seguidas no crea nada la
segunda vez (ya no quedan facturas vencidas sin caso).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import ConflictError, NotFoundError
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.portfolio.domain.cases import (
    CALL_OUTCOME_STATUSES,
    CaseStatus,
    InvoiceStage,
    debt_age_days,
    invoice_stage,
    is_negotiable,
)
from mavic.modules.portfolio.infrastructure.orm import CaseModel, DebtorModel, InvoiceModel
from mavic.modules.portfolio.infrastructure.repositories import (
    CaseRepository,
    CaseRow,
    CaseSort,
    InvoiceRepository,
    lock_company_portfolio,
)

# ---------------------------------------------------------------- vistas


@dataclass(frozen=True)
class DebtorView:
    id: uuid.UUID
    name: str
    document_number: str
    phone: str
    email: str

    @classmethod
    def from_model(cls, debtor: DebtorModel) -> "DebtorView":
        return cls(
            id=debtor.id,
            name=debtor.name,
            document_number=debtor.document_number,
            phone=debtor.phone,
            email=debtor.email,
        )


@dataclass(frozen=True)
class InvoiceView:
    id: uuid.UUID
    external_id: str
    description: str
    amount: Decimal
    currency: str
    due_date: date
    stage: InvoiceStage
    debtor_id: uuid.UUID
    debtor_name: str
    case_id: uuid.UUID | None
    case_number: int | None


@dataclass(frozen=True)
class CaseSummaryView:
    id: uuid.UUID
    number: int
    status: CaseStatus
    debtor: DebtorView
    invoice_count: int
    total_amount: Decimal
    oldest_due_date: date
    debt_age_days: int


@dataclass(frozen=True)
class CaseDetailView:
    summary: CaseSummaryView
    invoices: list[InvoiceView]


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class GenerationResult:
    cases_created: int
    cases_updated: int
    invoices_assigned: int


def _summary(row: CaseRow, today: date) -> CaseSummaryView:
    return CaseSummaryView(
        id=row.case.id,
        number=row.case.number,
        status=row.case.status,
        debtor=DebtorView.from_model(row.debtor),
        invoice_count=row.invoice_count,
        total_amount=row.total_amount,
        oldest_due_date=row.oldest_due_date,
        debt_age_days=debt_age_days(row.oldest_due_date, today),
    )


def _invoice_view(
    invoice: InvoiceModel, debtor_name: str, case_number: int | None, today: date
) -> InvoiceView:
    return InvoiceView(
        id=invoice.id,
        external_id=invoice.external_id,
        description=invoice.description,
        amount=invoice.amount,
        currency=invoice.currency,
        due_date=invoice.due_date,
        stage=invoice_stage(invoice.due_date, today),
        debtor_id=invoice.debtor_id,
        debtor_name=debtor_name,
        case_id=invoice.case_id,
        case_number=case_number,
    )


# ---------------------------------------------------------------- casos de uso


def generate_cases(session: Session, *, actor: Actor, clock: Clock) -> GenerationResult:
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()

    # Si dos operadores tocan "generar casos" a la vez, el segundo espera al
    # primero y después no encuentra nada nuevo: no se duplican casos.
    lock_company_portfolio(session, company_id)

    invoices = InvoiceRepository(session).unassigned_overdue(company_id, clock.today())
    if not invoices:
        return GenerationResult(cases_created=0, cases_updated=0, invoices_assigned=0)

    cases = CaseRepository(session)
    pending = cases.pending_by_debtor(company_id, {invoice.debtor_id for invoice in invoices})
    created: dict[uuid.UUID, CaseModel] = {}
    updated: set[uuid.UUID] = set()

    for invoice in invoices:
        case = pending.get(invoice.debtor_id) or created.get(invoice.debtor_id)
        if case is None:
            case = CaseModel(company_id=company_id, debtor_id=invoice.debtor_id)
            cases.add(case)
            session.flush()  # el caso recibe su id y su número
            created[invoice.debtor_id] = case
        elif invoice.debtor_id in pending:
            updated.add(invoice.debtor_id)
        invoice.case_id = case.id

    session.commit()
    return GenerationResult(
        cases_created=len(created), cases_updated=len(updated), invoices_assigned=len(invoices)
    )


def list_cases(
    session: Session,
    *,
    actor: Actor,
    clock: Clock,
    status: CaseStatus | None,
    sort: CaseSort,
    limit: int,
    offset: int,
) -> Page[CaseSummaryView]:
    actor.require(Permission.VIEW_PORTFOLIO)
    rows, total = CaseRepository(session).page(
        actor.require_company(), status=status, sort=sort, limit=limit, offset=offset
    )
    today = clock.today()
    return Page([_summary(row, today) for row in rows], total, limit, offset)


def get_case(session: Session, *, actor: Actor, clock: Clock, case_id: uuid.UUID) -> CaseDetailView:
    actor.require(Permission.VIEW_PORTFOLIO)
    return case_detail(session, company_id=actor.require_company(), clock=clock, case_id=case_id)


# ---------------------------------------------------------------- uso interno de otros módulos
#
# Estas funciones NO verifican permisos de usuario: las usan otros módulos que ya
# hicieron su propio control (por ejemplo, el agente de voz se autentica con un
# token y solo puede tocar el caso de su llamada). Siempre reciben la empresa,
# así nunca cruzan datos entre empresas.


@dataclass(frozen=True)
class CaseRef:
    id: uuid.UUID
    company_id: uuid.UUID


def case_detail(
    session: Session, *, company_id: uuid.UUID, clock: Clock, case_id: uuid.UUID
) -> CaseDetailView:
    row = CaseRepository(session).summary(company_id, case_id)
    if row is None:
        raise NotFoundError("El caso no existe.", code="CASE_NOT_FOUND")
    today = clock.today()
    invoices = InvoiceRepository(session).of_case(row.case.id)
    return CaseDetailView(
        summary=_summary(row, today),
        invoices=[_invoice_view(i, row.debtor.name, row.case.number, today) for i in invoices],
    )


def find_case_by_number(session: Session, number: int) -> CaseRef | None:
    """El caso con ese número ("caso 1042"). El número es único en todo el sistema."""
    case = CaseRepository(session).by_number(number)
    return None if case is None else CaseRef(id=case.id, company_id=case.company_id)


def record_call_outcome(
    session: Session, *, company_id: uuid.UUID, case_id: uuid.UUID, status: CaseStatus
) -> None:
    """Cambia el estado del caso según el resultado de una llamada.

    Bloquea el caso hasta el final de la transacción: si dos llamadas del mismo
    caso terminan a la vez, la segunda espera y ve el estado que dejó la primera.
    NO confirma la transacción: la confirma quien la llama, junto con el resto
    del registro de la llamada (todo o nada).
    """
    if status not in CALL_OUTCOME_STATUSES:
        raise ValueError(f"{status} no es un resultado de llamada")
    case = CaseRepository(session).get_for_update(company_id, case_id)
    if case is None:
        raise NotFoundError("El caso no existe.", code="CASE_NOT_FOUND")
    if not is_negotiable(case.status):
        raise ConflictError(
            "El caso ya tiene un resultado y no se puede negociar.", code="CASE_NOT_NEGOTIABLE"
        )
    case.status = status
    session.flush()


def list_invoices(
    session: Session,
    *,
    actor: Actor,
    clock: Clock,
    in_case: bool | None,
    overdue_only: bool,
    limit: int,
    offset: int,
) -> Page[InvoiceView]:
    actor.require(Permission.VIEW_PORTFOLIO)
    today = clock.today()
    rows, total = InvoiceRepository(session).page(
        actor.require_company(),
        in_case=in_case,
        overdue_before=today if overdue_only else None,
        limit=limit,
        offset=offset,
    )
    items = [_invoice_view(r.invoice, r.debtor_name, r.case_number, today) for r in rows]
    return Page(items, total, limit, offset)


def reopen_case_for_testing(session: Session, number: int) -> CaseRef:
    """Vuelve un caso a "pendiente" para poder probarlo otra vez con el agente.

    SOLO para pruebas locales (lo usa el comando `reopen-case`, que se niega a
    correr fuera de APP_ENV=local). En el uso real, un caso con resultado no se
    reabre: lo atiende una persona.

    Respeta la regla de la base: un deudor tiene como máximo UN caso pendiente.
    Las llamadas y acuerdos anteriores del caso se conservan como historial.
    """
    cases = CaseRepository(session)
    case = cases.by_number(number)
    if case is None:
        raise NotFoundError(f"No existe el caso {number}.", code="CASE_NOT_FOUND")
    if case.status != CaseStatus.PENDING:
        other = cases.pending_by_debtor(case.company_id, {case.debtor_id}).get(case.debtor_id)
        if other is not None:
            raise ConflictError(
                f"El deudor ya tiene otro caso pendiente (caso {other.number}).",
                code="OTHER_PENDING_CASE",
            )
        case.status = CaseStatus.PENDING
        session.commit()
    return CaseRef(id=case.id, company_id=case.company_id)
