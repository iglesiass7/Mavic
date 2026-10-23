"""Seguimiento de pagos de los acuerdos (registro manual).

- GET  /cases/{id}/agreements                               acuerdos del caso con sus cuotas
- POST /agreements/{id}/installments/{n}/payment            registrar el pago de una cuota
- POST /agreements/{id}/installments/{n}/undo-payment       anular un pago registrado por error

Ver: VIEW_PORTFOLIO. Registrar y anular: OPERATE_PORTFOLIO.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.modules.voice.application import payments

router = APIRouter(tags=["payments"])

Number = Annotated[int, Path(ge=1, le=120, description="Número de cuota (empieza en 1)")]


class InstallmentOut(BaseModel):
    number: int
    due_date: date
    amount: Decimal
    paid_on: date | None
    paid_recorded_at: datetime | None
    note: str | None
    overdue: bool


class AgreementTrackingOut(BaseModel):
    id: UUID
    case_id: UUID
    conversation_id: UUID
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
    status: str  # active (al día), fulfilled (cumplido), late (atrasado)
    paid_amount: Decimal
    pending_amount: Decimal
    next_due_date: date | None
    installments: list[InstallmentOut]

    @classmethod
    def from_view(cls, view: payments.AgreementView) -> "AgreementTrackingOut":
        data = dict(view.__dict__)
        data["status"] = view.status.value
        data["installments"] = [InstallmentOut(**i.__dict__) for i in view.installments]
        return cls(**data)


class PaymentIn(BaseModel):
    paid_on: date | None = Field(default=None, description="Día en que pagó (vacío: hoy)")
    note: str | None = Field(default=None, max_length=300, description="Ej.: 'transferencia'")


class UndoPaymentIn(BaseModel):
    reason: str = Field(min_length=1, max_length=300, description="Por qué se anula")


@router.get("/cases/{case_id}/agreements")
def case_agreements(
    case_id: UUID, session: SessionDep, actor: ActorDep, clock: ClockDep
) -> list[AgreementTrackingOut]:
    """Acuerdos del caso, del más nuevo al más viejo, con el estado de cada cuota."""
    views = payments.case_agreements(session, actor=actor, clock=clock, case_id=case_id)
    return [AgreementTrackingOut.from_view(view) for view in views]


@router.post("/agreements/{agreement_id}/installments/{number}/payment")
def record_payment(
    agreement_id: UUID,
    number: Number,
    body: PaymentIn,
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
) -> AgreementTrackingOut:
    """Marca la cuota como pagada. Si era la última, el caso pasa a cerrado."""
    view = payments.record_payment(
        session,
        actor=actor,
        clock=clock,
        agreement_id=agreement_id,
        number=number,
        paid_on=body.paid_on or clock.today(),
        note=body.note,
    )
    return AgreementTrackingOut.from_view(view)


@router.post("/agreements/{agreement_id}/installments/{number}/undo-payment")
def undo_payment(
    agreement_id: UUID,
    number: Number,
    body: UndoPaymentIn,
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
) -> AgreementTrackingOut:
    """Deshace un pago registrado por error. El motivo queda en la auditoría."""
    view = payments.undo_payment(
        session,
        actor=actor,
        clock=clock,
        agreement_id=agreement_id,
        number=number,
        reason=body.reason,
    )
    return AgreementTrackingOut.from_view(view)
