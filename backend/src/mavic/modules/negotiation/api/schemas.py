"""Contratos de la API de negociación.

Igual que en la cartera, montos y porcentajes viajan como TEXTO ("108000.00").
Al ENVIAR una regla se aceptan número o texto: `500000` y `"500000"` valen igual.

Las reglas son "planas" (un campo por valor) en vez de anidadas: es más fácil de
completar en un formulario y en Swagger.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from mavic.modules.negotiation.application.offers import CaseOffersView
from mavic.modules.negotiation.application.rules import RuleData, RuleView
from mavic.modules.negotiation.domain.offers import CallOffer, InstallmentsOffer, SinglePaymentOffer
from mavic.modules.negotiation.domain.rules import Interval, PaymentTerms, RuleConditions
from mavic.modules.portfolio.domain.cases import CaseStatus

# Tipos con límites de FORMATO. Las reglas de negocio (mínimo <= máximo, descuento
# menor a 100 %...) se validan en el dominio, en un solo lugar.
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Percent = Annotated[Decimal, Field(max_digits=5, decimal_places=2)]
Days = Annotated[int, Field(ge=0, le=100_000)]  # protege a la columna INTEGER de números enormes
Count = Annotated[int, Field(ge=0, le=100_000)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class RuleIn(BaseModel):
    name: Name
    description: Description = ""
    min_amount: Money = Decimal("0")
    max_amount: Money | None = Field(default=None, description="Vacío = sin tope")
    min_debt_age_days: Days = 0
    max_debt_age_days: Days | None = Field(default=None, description="Vacío = sin tope")
    min_invoice_count: Count = 1
    max_invoice_count: Count | None = Field(default=None, description="Vacío = sin tope")
    discount_pct: Percent = Field(description="Descuento por pago único (0 a 99,99)")
    payment_days: Days = Field(description="Días para pagar o para la primera cuota")
    max_installments: Count = Field(description="1 = solo pago único")
    interest_pct: Percent = Field(description="Interés total del plan en cuotas (0 a 100)")
    is_active: bool = True

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Mora alta con plan extendido",
                    "description": "Mora desde 60 días: hasta 6 cuotas.",
                    "min_amount": "0",
                    "max_amount": "500000",
                    "min_debt_age_days": 60,
                    "max_debt_age_days": None,
                    "min_invoice_count": 1,
                    "max_invoice_count": 12,
                    "discount_pct": "10",
                    "payment_days": 5,
                    "max_installments": 6,
                    "interest_pct": "12",
                    "is_active": True,
                }
            ]
        }
    }

    def to_data(self) -> RuleData:
        return RuleData(
            name=self.name,
            description=self.description,
            conditions=RuleConditions(
                amount=Interval(self.min_amount, self.max_amount),
                debt_age_days=Interval(self.min_debt_age_days, self.max_debt_age_days),
                invoice_count=Interval(self.min_invoice_count, self.max_invoice_count),
            ),
            terms=PaymentTerms(
                discount_pct=self.discount_pct,
                payment_days=self.payment_days,
                max_installments=self.max_installments,
                interest_pct=self.interest_pct,
            ),
            is_active=self.is_active,
        )


class RuleOut(BaseModel):
    id: UUID
    name: str
    description: str
    min_amount: Decimal
    max_amount: Decimal | None
    min_debt_age_days: int
    max_debt_age_days: int | None
    min_invoice_count: int
    max_invoice_count: int | None
    discount_pct: Decimal
    payment_days: int
    max_installments: int
    interest_pct: Decimal
    is_active: bool

    @classmethod
    def from_view(cls, rule: RuleView) -> "RuleOut":
        c, t = rule.conditions, rule.terms
        return cls(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            min_amount=c.amount.minimum,
            max_amount=c.amount.maximum,
            min_debt_age_days=c.debt_age_days.minimum,
            max_debt_age_days=c.debt_age_days.maximum,
            min_invoice_count=c.invoice_count.minimum,
            max_invoice_count=c.invoice_count.maximum,
            discount_pct=t.discount_pct,
            payment_days=t.payment_days,
            max_installments=t.max_installments,
            interest_pct=t.interest_pct,
            is_active=rule.is_active,
        )


# ---------------------------------------------------------------- ofertas


class SinglePaymentOut(BaseModel):
    offer_id: str
    original_amount: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    pay_by: date

    @classmethod
    def from_offer(cls, offer: SinglePaymentOffer) -> "SinglePaymentOut":
        return cls(
            offer_id=offer.offer_id,
            original_amount=offer.original_amount,
            discount_pct=offer.discount_pct,
            discount_amount=offer.discount_amount,
            total_amount=offer.total_amount,
            pay_by=offer.pay_by,
        )


class InstallmentOut(BaseModel):
    number: int
    due_date: date
    amount: Decimal


class InstallmentsOut(BaseModel):
    offer_id: str
    original_amount: Decimal
    interest_pct: Decimal
    interest_amount: Decimal
    total_amount: Decimal
    installment_count: int
    installment_amount: Decimal
    schedule: list[InstallmentOut]

    @classmethod
    def from_offer(cls, offer: InstallmentsOffer) -> "InstallmentsOut":
        return cls(
            offer_id=offer.offer_id,
            original_amount=offer.original_amount,
            interest_pct=offer.interest_pct,
            interest_amount=offer.interest_amount,
            total_amount=offer.total_amount,
            installment_count=offer.installment_count,
            installment_amount=offer.installment_amount,
            schedule=[
                InstallmentOut(number=i.number, due_date=i.due_date, amount=i.amount)
                for i in offer.schedule
            ],
        )


class RuleRefOut(BaseModel):
    id: UUID
    name: str


class CallOfferOut(BaseModel):
    """Una oferta tal como la recibe el agente nuevo (sin fechas, cuotas iguales)."""

    priority: int
    offer_id: str
    kind: str  # PAGO_UNICO | CUOTAS
    total_amount: Decimal
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    installment_count: int
    installment_amount: Decimal | None

    @classmethod
    def from_offer(cls, offer: CallOffer) -> "CallOfferOut":
        return cls(**{**offer.__dict__, "kind": offer.kind.value})


class CaseOffersOut(BaseModel):
    case_id: UUID
    case_number: int
    case_status: CaseStatus
    currency: str
    total_amount: Decimal
    debt_age_days: int
    invoice_count: int
    rule: RuleRefOut | None
    has_offer: bool
    reason: str | None = Field(description="Por qué no hay oferta, si no la hay")
    single_payment: SinglePaymentOut | None
    installments: InstallmentsOut | None
    call_offers: list[CallOfferOut] = Field(
        description="Las ofertas en el orden en que las presenta el agente al llamar (ADR-034)"
    )

    @classmethod
    def from_view(cls, view: CaseOffersView) -> "CaseOffersOut":
        offers = view.offers
        return cls(
            case_id=view.case_id,
            case_number=view.case_number,
            case_status=view.case_status,
            currency=view.currency,
            total_amount=view.facts.total_amount,
            debt_age_days=view.facts.debt_age_days,
            invoice_count=view.facts.invoice_count,
            rule=RuleRefOut(id=view.rule.id, name=view.rule.name) if view.rule else None,
            has_offer=offers is not None,
            reason=view.reason.value if view.reason else None,
            single_payment=SinglePaymentOut.from_offer(offers.single_payment) if offers else None,
            installments=(
                InstallmentsOut.from_offer(offers.installments)
                if offers and offers.installments
                else None
            ),
            call_offers=[CallOfferOut.from_offer(o) for o in view.call_offers],
        )
