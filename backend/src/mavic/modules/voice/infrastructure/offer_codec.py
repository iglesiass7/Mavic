"""Cómo se guardan las ofertas de una llamada en la columna JSON.

Montos como texto ("108000.00") y fechas en formato ISO ("2026-10-21"): así
vuelven EXACTOS al leerlos. Un número JSON se leería como float.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from mavic.modules.negotiation.domain.offers import (
    Installment,
    InstallmentsOffer,
    SinglePaymentOffer,
)
from mavic.modules.voice.domain.call_offers import CallOffers


def encode(offers: CallOffers) -> dict[str, Any]:
    single, plan = offers.single_payment, offers.installments
    return {
        "total_amount": str(offers.total_amount),
        "currency": offers.currency,
        "rule_name": offers.rule_name,
        "no_offer_reason": offers.no_offer_reason,
        "single_payment": None
        if single is None
        else {
            "offer_id": single.offer_id,
            "original_amount": str(single.original_amount),
            "discount_pct": str(single.discount_pct),
            "discount_amount": str(single.discount_amount),
            "total_amount": str(single.total_amount),
            "pay_by": single.pay_by.isoformat(),
        },
        "installments": None
        if plan is None
        else {
            "offer_id": plan.offer_id,
            "original_amount": str(plan.original_amount),
            "interest_pct": str(plan.interest_pct),
            "interest_amount": str(plan.interest_amount),
            "total_amount": str(plan.total_amount),
            "installment_count": plan.installment_count,
            "installment_amount": str(plan.installment_amount),
            "schedule": [
                {"number": i.number, "due_date": i.due_date.isoformat(), "amount": str(i.amount)}
                for i in plan.schedule
            ],
        },
    }


def decode(data: dict[str, Any]) -> CallOffers:
    single, plan = data["single_payment"], data["installments"]
    return CallOffers(
        total_amount=Decimal(data["total_amount"]),
        currency=data["currency"],
        rule_name=data["rule_name"],
        no_offer_reason=data["no_offer_reason"],
        single_payment=None
        if single is None
        else SinglePaymentOffer(
            offer_id=single["offer_id"],
            original_amount=Decimal(single["original_amount"]),
            discount_pct=Decimal(single["discount_pct"]),
            discount_amount=Decimal(single["discount_amount"]),
            total_amount=Decimal(single["total_amount"]),
            pay_by=date.fromisoformat(single["pay_by"]),
        ),
        installments=None
        if plan is None
        else InstallmentsOffer(
            offer_id=plan["offer_id"],
            original_amount=Decimal(plan["original_amount"]),
            interest_pct=Decimal(plan["interest_pct"]),
            interest_amount=Decimal(plan["interest_amount"]),
            total_amount=Decimal(plan["total_amount"]),
            installment_count=plan["installment_count"],
            installment_amount=Decimal(plan["installment_amount"]),
            schedule=[
                Installment(
                    number=i["number"],
                    due_date=date.fromisoformat(i["due_date"]),
                    amount=Decimal(i["amount"]),
                )
                for i in plan["schedule"]
            ],
        ),
    )
