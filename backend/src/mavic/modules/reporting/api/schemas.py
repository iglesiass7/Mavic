"""Contrato de GET /dashboard. Montos como TEXTO ("56900.00"), igual que el resto de la API."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from mavic.modules.portfolio.application.summary import Bucket
from mavic.modules.reporting.application.dashboard import Dashboard


class BucketOut(BaseModel):
    key: str  # un estado de caso ("pending") o un tramo de atraso ("31_60")
    cases: int
    amount: Decimal

    @classmethod
    def from_bucket(cls, bucket: Bucket) -> "BucketOut":
        return cls(key=bucket.key, cases=bucket.cases, amount=bucket.amount)


class PortfolioOut(BaseModel):
    currency: str
    cases_total: int
    amount_total: Decimal
    by_status: list[BucketOut]
    in_progress_cases: int
    in_progress_amount: Decimal
    in_progress_by_age: list[BucketOut]
    unassigned_overdue_invoices: int
    unassigned_overdue_amount: Decimal
    upcoming_invoices: int
    upcoming_amount: Decimal


class AgentOut(BaseModel):
    calls: int
    identity_verified: int
    calls_by_result: dict[str, int]
    calls_without_result: int
    last_call_at: datetime | None
    agreements: int
    agreements_single_payment: int
    agreements_installments: int
    agreed_original_amount: Decimal
    agreed_amount: Decimal


class DashboardOut(BaseModel):
    as_of: date
    portfolio: PortfolioOut
    agent: AgentOut

    @classmethod
    def from_view(cls, view: Dashboard) -> "DashboardOut":
        p = view.portfolio
        return cls(
            as_of=view.as_of,
            portfolio=PortfolioOut(
                **{
                    **p.__dict__,
                    "by_status": [BucketOut.from_bucket(b) for b in p.by_status],
                    "in_progress_by_age": [BucketOut.from_bucket(b) for b in p.in_progress_by_age],
                }
            ),
            agent=AgentOut(**view.agent.__dict__),
        )
