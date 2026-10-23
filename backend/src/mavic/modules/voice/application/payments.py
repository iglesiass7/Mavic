"""Seguimiento de pagos de los acuerdos (registro manual).

    deudor acepta ──> acuerdo + cuotas con fecha (al llegar el resultado de la llamada)
    operador ───────> "Registrar pago" en una cuota (con el día en que pagó)
    última cuota paga ──> acuerdo CUMPLIDO y el caso pasa a CERRADO
    una fecha vencida sin pago ──> acuerdo ATRASADO (se calcula, no se guarda)

Equivocarse es posible: "Anular pago" deshace el registro (con un motivo, que
queda en la auditoría). Si el caso se había cerrado por ese pago, vuelve a
"acuerdo de pago".
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import BusinessRuleViolationError, ConflictError, NotFoundError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditAction, Subject
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.voice.domain.payments import (
    DEFAULT_PAYMENT_DAYS,
    AgreementStatus,
    InstallmentState,
    agreement_status,
    plan_installments,
    validate_payment_date,
)
from mavic.modules.voice.infrastructure.orm import (
    AgreementInstallmentModel,
    ConversationModel,
    PaymentAgreementModel,
)
from mavic.modules.voice.infrastructure.repositories import AgreementRepository

MAX_NOTE = 300


# ---------------------------------------------------------------- al crear un acuerdo


def payment_days_of(conversation: ConversationModel) -> int:
    """El plazo de la regla con la que se llamó (está en la foto de la llamada)."""
    rule = (conversation.initiation_payload or {}).get("rule") or {}
    days = rule.get("payment_days") if isinstance(rule, dict) else None
    return days if isinstance(days, int) and days >= 0 else DEFAULT_PAYMENT_DAYS


def add_installments(
    session: Session, agreement: PaymentAgreementModel, *, agreed_on: date, payment_days: int
) -> None:
    """Crea las cuotas de un acuerdo nuevo (en la misma transacción que el acuerdo).

    Si el acuerdo trae fechas pactadas (flujo anterior), se usan esas. Si no,
    se arman con el plazo de la regla.
    """
    session.flush()  # el acuerdo necesita su id
    repository = AgreementRepository(session)
    if agreement.schedule:
        for line in agreement.schedule:
            repository.add_installment(
                AgreementInstallmentModel(
                    company_id=agreement.company_id,
                    agreement_id=agreement.id,
                    number=int(line["number"]),
                    due_date=date.fromisoformat(str(line["due_date"])),
                    amount=Decimal(str(line["amount"])),
                )
            )
        return
    each = agreement.installment_amount or agreement.total_amount
    for planned in plan_installments(
        agreed_on=agreed_on,
        payment_days=payment_days,
        count=agreement.installment_count,
        amount=each,
    ):
        repository.add_installment(
            AgreementInstallmentModel(
                company_id=agreement.company_id,
                agreement_id=agreement.id,
                number=planned.number,
                due_date=planned.due_date,
                amount=planned.amount,
            )
        )


# ---------------------------------------------------------------- vistas


@dataclass(frozen=True)
class InstallmentView:
    number: int
    due_date: date
    amount: Decimal
    paid_on: date | None
    paid_recorded_at: datetime | None
    note: str | None
    overdue: bool  # vencida y sin pagar


@dataclass(frozen=True)
class AgreementView:
    id: uuid.UUID
    case_id: uuid.UUID
    conversation_id: uuid.UUID
    offer_id: str
    modality: str
    currency: str
    original_amount: Decimal
    total_amount: Decimal
    installment_count: int
    installment_amount: Decimal | None
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    created_at: datetime
    status: AgreementStatus
    paid_amount: Decimal
    pending_amount: Decimal
    next_due_date: date | None  # la próxima cuota sin pagar
    installments: list[InstallmentView]


def _view(
    agreement: PaymentAgreementModel, installments: list[AgreementInstallmentModel], today: date
) -> AgreementView:
    states = [InstallmentState(i.due_date, i.amount, i.paid_on) for i in installments]
    unpaid = [i for i in installments if i.paid_on is None]
    paid = sum((i.amount for i in installments if i.paid_on is not None), Decimal("0"))
    return AgreementView(
        id=agreement.id,
        case_id=agreement.case_id,
        conversation_id=agreement.conversation_id,
        offer_id=agreement.offer_id,
        modality=agreement.modality,
        currency=agreement.currency,
        original_amount=agreement.original_amount,
        total_amount=agreement.total_amount,
        installment_count=agreement.installment_count,
        installment_amount=agreement.installment_amount,
        discount_pct=agreement.discount_pct,
        discount_amount=agreement.discount_amount,
        created_at=agreement.created_at,
        # Un acuerdo viejo sin cuotas (no debería existir después de la migración) va como al día.
        status=agreement_status(states, today) if states else AgreementStatus.ACTIVE,
        paid_amount=paid,
        pending_amount=sum((i.amount for i in unpaid), Decimal("0")),
        next_due_date=min((i.due_date for i in unpaid), default=None),
        installments=[
            InstallmentView(
                number=i.number,
                due_date=i.due_date,
                amount=i.amount,
                paid_on=i.paid_on,
                paid_recorded_at=i.paid_recorded_at,
                note=i.note,
                overdue=i.paid_on is None and i.due_date < today,
            )
            for i in installments
        ],
    )


def case_agreements(
    session: Session, *, actor: Actor, clock: Clock, case_id: uuid.UUID
) -> list[AgreementView]:
    """Los acuerdos de un caso, del más nuevo al más viejo, con sus cuotas."""
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()
    repository = AgreementRepository(session)
    agreements = repository.of_case(company_id, case_id)
    installments = repository.installments_of([a.id for a in agreements])
    today = clock.today()
    return [_view(a, installments.get(a.id, []), today) for a in agreements]


# ---------------------------------------------------------------- registrar y anular


def _locked(
    session: Session, company_id: uuid.UUID, agreement_id: uuid.UUID, number: int
) -> tuple[PaymentAgreementModel, AgreementInstallmentModel]:
    repository = AgreementRepository(session)
    agreement = repository.get_for_update(company_id, agreement_id)
    if agreement is None:
        raise NotFoundError("El acuerdo no existe.", code="AGREEMENT_NOT_FOUND")
    installment = repository.installment_for_update(agreement.id, number)
    if installment is None:
        raise NotFoundError("Esa cuota no existe.", code="INSTALLMENT_NOT_FOUND")
    return agreement, installment


def _label(installment: AgreementInstallmentModel, agreement: PaymentAgreementModel) -> str:
    if agreement.installment_count == 1:
        return "el pago único"
    return f"la cuota {installment.number} de {agreement.installment_count}"


def record_payment(
    session: Session,
    *,
    actor: Actor,
    clock: Clock,
    agreement_id: uuid.UUID,
    number: int,
    paid_on: date,
    note: str | None,
) -> AgreementView:
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()
    agreement, installment = _locked(session, company_id, agreement_id, number)
    if installment.paid_on is not None:
        raise ConflictError("Esa cuota ya figura como pagada.", code="INSTALLMENT_ALREADY_PAID")
    today = clock.today()
    agreed_on = agreement.created_at.astimezone(clock.zone()).date()
    validate_payment_date(paid_on, agreed_on=agreed_on, today=today)

    installment.paid_on = paid_on
    installment.paid_recorded_at = clock.now()
    installment.paid_recorded_by = actor.user_id
    installment.note = (note or "").strip()[:MAX_NOTE] or None

    brief = portfolio.case_briefs(session, company_id=company_id, case_ids={agreement.case_id})[
        agreement.case_id
    ]
    subject = Subject("case", str(agreement.case_id), f"Caso #{brief.number}")
    audit.record(
        session,
        company_id=company_id,
        actor=actor,
        action=AuditAction.PAYMENT_RECORDED,
        subject=subject,
        summary=f"Registró el pago de {_label(installment, agreement)} del caso #{brief.number} "
        f"({brief.debtor_name}), pagado el {paid_on:%d/%m/%Y}.",
        details=_payment_details(installment, agreement),
    )

    installments = AgreementRepository(session).installments_of([agreement.id])[agreement.id]
    view = _view(agreement, installments, today)
    if view.status is AgreementStatus.FULFILLED:
        portfolio.settle_case(session, company_id=company_id, case_id=agreement.case_id)
        audit.record(
            session,
            company_id=company_id,
            action=AuditAction.AGREEMENT_FULFILLED,
            subject=subject,
            summary=f"El acuerdo del caso #{brief.number} quedó cumplido y el caso se cerró.",
        )
    session.commit()
    return view


def undo_payment(
    session: Session,
    *,
    actor: Actor,
    clock: Clock,
    agreement_id: uuid.UUID,
    number: int,
    reason: str,
) -> AgreementView:
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()
    reason = reason.strip()
    if not reason:
        raise BusinessRuleViolationError(
            "Contá por qué se anula el pago (queda en la auditoría).", code="UNDO_REASON_REQUIRED"
        )
    agreement, installment = _locked(session, company_id, agreement_id, number)
    if installment.paid_on is None:
        raise ConflictError("Esa cuota no figura como pagada.", code="INSTALLMENT_NOT_PAID")

    details = _payment_details(installment, agreement) | {"motivo": reason[:MAX_NOTE]}
    repository = AgreementRepository(session)
    before = [
        InstallmentState(i.due_date, i.amount, i.paid_on)
        for i in repository.installments_of([agreement.id])[agreement.id]
    ]
    was_fulfilled = agreement_status(before, clock.today()) is AgreementStatus.FULFILLED
    installment.paid_on = None
    installment.paid_recorded_at = None
    installment.paid_recorded_by = None
    installment.note = None
    if was_fulfilled:
        # El caso se había cerrado por este acuerdo: vuelve a "acuerdo de pago".
        portfolio.unsettle_case(session, company_id=company_id, case_id=agreement.case_id)

    brief = portfolio.case_briefs(session, company_id=company_id, case_ids={agreement.case_id})[
        agreement.case_id
    ]
    audit.record(
        session,
        company_id=company_id,
        actor=actor,
        action=AuditAction.PAYMENT_UNDONE,
        subject=Subject("case", str(agreement.case_id), f"Caso #{brief.number}"),
        summary=f"Anuló el pago de {_label(installment, agreement)} del caso #{brief.number}. "
        f"Motivo: {reason[:MAX_NOTE]}",
        details=details,
    )
    session.commit()
    installments = AgreementRepository(session).installments_of([agreement.id])[agreement.id]
    return _view(agreement, installments, clock.today())


def _payment_details(
    installment: AgreementInstallmentModel, agreement: PaymentAgreementModel
) -> dict[str, Any]:
    return {
        "cuota": installment.number,
        "de": agreement.installment_count,
        "importe": str(installment.amount),
        "moneda": agreement.currency,
        "vencimiento": installment.due_date.isoformat(),
        "pagada_el": installment.paid_on.isoformat() if installment.paid_on else None,
        "nota": installment.note,
    }


# ---------------------------------------------------------------- tablero


@dataclass(frozen=True)
class PaymentTotals:
    active: int
    fulfilled: int
    late: int
    collected_amount: Decimal  # lo que ya pagaron (cuotas registradas)
    pending_amount: Decimal  # lo que falta cobrar de los acuerdos
    overdue_amount: Decimal  # de lo que falta, lo que ya venció


def payment_totals(session: Session, *, company_id: uuid.UUID, today: date) -> PaymentTotals:
    """Para el tablero (no chequea permisos: lo llama reportes, que ya los chequeó)."""
    by_agreement = AgreementRepository(session).all_installments(company_id)
    counts = dict.fromkeys(AgreementStatus, 0)
    collected = pending = overdue = Decimal("0")
    for installments in by_agreement.values():
        states = [InstallmentState(i.due_date, i.amount, i.paid_on) for i in installments]
        counts[agreement_status(states, today)] += 1
        for i in installments:
            if i.paid_on is not None:
                collected += i.amount
            else:
                pending += i.amount
                if i.due_date < today:
                    overdue += i.amount
    return PaymentTotals(
        active=counts[AgreementStatus.ACTIVE],
        fulfilled=counts[AgreementStatus.FULFILLED],
        late=counts[AgreementStatus.LATE],
        collected_amount=collected,
        pending_amount=pending,
        overdue_amount=overdue,
    )
