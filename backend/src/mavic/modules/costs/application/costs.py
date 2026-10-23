"""Medidor de costos: el uso del mes por las tarifas, y las tarifas mismas.

GET /costs?month=2026-10
    ├─ minutos de llamada por día  (voice.application.usage)
    ├─ avisos mandados por día     (notices.application.sending)
    └─ tarifas de la empresa       (esta tabla)
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import BusinessRuleViolationError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditAction, Subject, changes
from mavic.modules.costs.domain.costs import (
    MAX_RATE,
    NO_RATES,
    ZERO,
    BudgetStatus,
    Concept,
    Rates,
    budget_status,
    minutes,
    money,
    month_span,
    project,
)
from mavic.modules.costs.infrastructure.orm import CostRatesModel
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.notices.application.sending import DailyNoticeUsage, sent_by_day
from mavic.modules.notices.domain.notices import Channel
from mavic.modules.voice.application.usage import calls_by_day

# ---------------------------------------------------------------- tarifas

RATE_SCALE = Decimal("0.0001")  # las tarifas se guardan con 4 decimales


def _rates_of(row: CostRatesModel | None) -> Rates:
    if row is None:
        return NO_RATES
    return Rates(row.currency, row.call_minute, row.email, row.whatsapp, row.monthly_budget)


@dataclass(frozen=True)
class RatesView:
    rates: Rates
    configured: bool  # False: nunca se cargaron (todo en 0)


def get_rates(session: Session, *, actor: Actor) -> RatesView:
    actor.require(Permission.VIEW_COSTS)
    row = session.get(CostRatesModel, actor.require_company())
    return RatesView(_rates_of(row), row is not None)


def update_rates(session: Session, *, actor: Actor, rates: Rates) -> RatesView:
    actor.require(Permission.MANAGE_COSTS)
    company_id = actor.require_company()
    for value in (rates.call_minute, rates.email, rates.whatsapp):
        if value < 0 or value > MAX_RATE:
            raise BusinessRuleViolationError(
                f"Cada tarifa va de 0 a {MAX_RATE} por unidad.", code="COST_RATE_INVALID"
            )
    if rates.monthly_budget is not None and rates.monthly_budget <= 0:
        raise BusinessRuleViolationError(
            "El tope mensual tiene que ser mayor que 0 (o vacío para no usarlo).",
            code="COST_BUDGET_INVALID",
        )
    currency = rates.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise BusinessRuleViolationError(
            "La moneda es un código de 3 letras (USD, ARS…).", code="COST_CURRENCY_INVALID"
        )

    # Siempre con la misma escala que guarda la base ("0.15" -> "0.1500"): así el
    # antes / después de la auditoría solo muestra lo que de verdad cambió.
    rates = Rates(
        currency=currency,
        call_minute=rates.call_minute.quantize(RATE_SCALE),
        email=rates.email.quantize(RATE_SCALE),
        whatsapp=rates.whatsapp.quantize(RATE_SCALE),
        monthly_budget=None if rates.monthly_budget is None else money(rates.monthly_budget),
    )
    row = session.get(CostRatesModel, company_id)
    before = _readable(_rates_of(row))
    if row is None:
        row = CostRatesModel(company_id=company_id)
        session.add(row)
    row.currency = currency
    row.call_minute = rates.call_minute
    row.email = rates.email
    row.whatsapp = rates.whatsapp
    row.monthly_budget = rates.monthly_budget
    new = _rates_of(row)
    diff = changes(before, _readable(new))
    if diff:
        audit.record(
            session,
            company_id=company_id,
            actor=actor,
            action=AuditAction.COST_RATES_UPDATED,
            subject=Subject("settings", "cost_rates", "Tarifas del medidor de costos"),
            summary=f"Cambió las tarifas: {', '.join(k.lower() for k in diff)}.",
            details={"cambios": diff},
        )
    session.commit()
    return RatesView(new, True)


def _readable(r: Rates) -> dict[str, object]:
    return {
        "Moneda": r.currency,
        "Minuto de llamada": str(r.call_minute),
        "Email": str(r.email),
        "WhatsApp": str(r.whatsapp),
        "Tope mensual": None if r.monthly_budget is None else str(r.monthly_budget),
    }


# ---------------------------------------------------------------- el mes


@dataclass(frozen=True)
class ConceptCost:
    concept: Concept
    quantity: Decimal  # minutos (con decimales), emails o mensajes
    count: int  # llamadas, emails o mensajes
    rate: Decimal
    cost: Decimal
    projected_cost: Decimal


@dataclass(frozen=True)
class DailyCost:
    day: date
    cost: Decimal


@dataclass(frozen=True)
class MonthCosts:
    month: date
    currency: str
    rates_configured: bool
    days_in_month: int
    days_counted: int
    concepts: list[ConceptCost]
    total: Decimal
    projected_total: Decimal
    monthly_budget: Decimal | None
    budget_status: BudgetStatus
    daily: list[DailyCost]  # un renglón por día del mes, con 0 si no hubo uso


def month_costs(session: Session, *, actor: Actor, clock: Clock, month: date | None) -> MonthCosts:
    actor.require(Permission.VIEW_COSTS)
    company_id = actor.require_company()
    today = clock.today()
    span = month_span(month or today, today)
    zone = clock.zone()
    since = datetime.combine(span.month, time.min, tzinfo=zone)
    next_month = date(span.month.year + span.month.month // 12, span.month.month % 12 + 1, 1)
    until = datetime.combine(next_month, time.min, tzinfo=zone)

    row = session.get(CostRatesModel, company_id)
    rates = _rates_of(row)
    calls = calls_by_day(session, company_id=company_id, since=since, until=until, zone=zone.key)
    notices = sent_by_day(session, company_id=company_id, since=since, until=until, zone=zone.key)

    seconds = sum(c.seconds for c in calls)
    usage: dict[Concept, tuple[Decimal, int]] = {
        Concept.CALLS: (minutes(seconds), sum(c.calls for c in calls)),
        Concept.EMAIL: _sent(notices, Channel.EMAIL),
        Concept.WHATSAPP: _sent(notices, Channel.WHATSAPP),
    }
    concepts = []
    for concept, (quantity, count) in usage.items():
        cost = money(quantity * rates.of(concept))
        concepts.append(
            ConceptCost(
                concept, money(quantity), count, rates.of(concept), cost, project(cost, span)
            )
        )
    total = sum((c.cost for c in concepts), ZERO)
    projected = sum((c.projected_cost for c in concepts), ZERO)

    by_day: dict[date, Decimal] = {}
    for c in calls:
        by_day[c.day] = by_day.get(c.day, ZERO) + minutes(c.seconds) * rates.call_minute
    for n in notices:
        rate = rates.email if n.channel is Channel.EMAIL else rates.whatsapp
        by_day[n.day] = by_day.get(n.day, ZERO) + n.sent * rate
    daily = [
        DailyCost(day, money(by_day.get(day, ZERO)))
        for day in (span.month.replace(day=d) for d in range(1, span.days_in_month + 1))
    ]

    return MonthCosts(
        month=span.month,
        currency=rates.currency,
        rates_configured=row is not None,
        days_in_month=span.days_in_month,
        days_counted=span.days_counted,
        concepts=concepts,
        total=money(total),
        projected_total=money(projected),
        monthly_budget=rates.monthly_budget,
        budget_status=budget_status(total, projected, rates.monthly_budget),
        daily=daily,
    )


def _sent(notices: list[DailyNoticeUsage], channel: Channel) -> tuple[Decimal, int]:
    count = sum(n.sent for n in notices if n.channel is channel)
    return Decimal(count), count
