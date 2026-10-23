"""Medidor de costos.

- GET /costs?month=2026-10   uso del mes × tarifas, proyección y tope (VIEW_COSTS)
- GET /cost-rates            las tarifas (VIEW_COSTS)
- PUT /cost-rates            cambiarlas (MANAGE_COSTS: administración)

Montos como texto ("12.50"), igual que el resto de la API.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.core.errors import BusinessRuleViolationError
from mavic.modules.costs.application import costs
from mavic.modules.costs.domain.costs import BudgetStatus, Concept, Rates

router = APIRouter(tags=["costs"])

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class RatesOut(BaseModel):
    currency: str
    call_minute: Decimal
    email: Decimal
    whatsapp: Decimal
    monthly_budget: Decimal | None
    configured: bool

    @classmethod
    def from_view(cls, view: costs.RatesView) -> "RatesOut":
        r = view.rates
        return cls(
            currency=r.currency,
            call_minute=r.call_minute,
            email=r.email,
            whatsapp=r.whatsapp,
            monthly_budget=r.monthly_budget,
            configured=view.configured,
        )


class RatesIn(BaseModel):
    currency: str = Field(default="USD", min_length=3, max_length=3)
    call_minute: Decimal = Field(ge=0, decimal_places=4)
    email: Decimal = Field(ge=0, decimal_places=4)
    whatsapp: Decimal = Field(ge=0, decimal_places=4)
    monthly_budget: Decimal | None = Field(default=None, gt=0, decimal_places=2)


class ConceptCostOut(BaseModel):
    concept: Concept
    quantity: Decimal
    count: int
    rate: Decimal
    cost: Decimal
    projected_cost: Decimal


class DailyCostOut(BaseModel):
    day: date
    cost: Decimal


class MonthCostsOut(BaseModel):
    month: str  # "2026-10"
    currency: str
    rates_configured: bool
    days_in_month: int
    days_counted: int
    concepts: list[ConceptCostOut]
    total: Decimal
    projected_total: Decimal
    monthly_budget: Decimal | None
    budget_status: BudgetStatus
    daily: list[DailyCostOut]


@router.get("/costs")
def month_costs(
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    month: Annotated[str | None, Query(description="Mes AAAA-MM (vacío: el actual)")] = None,
) -> MonthCostsOut:
    first = None
    if month:
        match = _MONTH.match(month)
        if not match:
            raise BusinessRuleViolationError("El mes va como AAAA-MM.", code="MONTH_INVALID")
        first = date(int(match.group(1)), int(match.group(2)), 1)
    view = costs.month_costs(session, actor=actor, clock=clock, month=first)
    return MonthCostsOut(
        month=f"{view.month:%Y-%m}",
        currency=view.currency,
        rates_configured=view.rates_configured,
        days_in_month=view.days_in_month,
        days_counted=view.days_counted,
        concepts=[ConceptCostOut(**c.__dict__) for c in view.concepts],
        total=view.total,
        projected_total=view.projected_total,
        monthly_budget=view.monthly_budget,
        budget_status=view.budget_status,
        daily=[DailyCostOut(**d.__dict__) for d in view.daily],
    )


@router.get("/cost-rates")
def get_rates(session: SessionDep, actor: ActorDep) -> RatesOut:
    return RatesOut.from_view(costs.get_rates(session, actor=actor))


@router.put("/cost-rates")
def update_rates(body: RatesIn, session: SessionDep, actor: ActorDep) -> RatesOut:
    rates = Rates(
        currency=body.currency,
        call_minute=body.call_minute,
        email=body.email,
        whatsapp=body.whatsapp,
        monthly_budget=body.monthly_budget,
    )
    return RatesOut.from_view(costs.update_rates(session, actor=actor, rates=rates))
