"""Facturas a las que les toca un aviso (lo usa el módulo de avisos).

La cartera no sabe qué es un aviso: solo responde "qué facturas sin caso vencen
entre tal y tal día, y cómo contactar a su deudor".
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.modules.portfolio.infrastructure.repositories import InvoiceRepository


@dataclass(frozen=True)
class InvoiceContact:
    invoice_id: uuid.UUID
    external_id: str
    description: str
    amount: Decimal
    currency: str
    due_date: date
    debtor_id: uuid.UUID
    debtor_name: str
    debtor_email: str | None
    debtor_phone: str | None


def invoices_due_between(
    session: Session, *, company_id: uuid.UUID, first: date, last: date
) -> list[InvoiceContact]:
    """No controla permisos: la llama otro caso de uso que ya los controló."""
    rows = InvoiceRepository(session).due_between_with_debtor(company_id, first, last)
    return [
        InvoiceContact(
            invoice_id=invoice.id,
            external_id=invoice.external_id,
            description=invoice.description,
            amount=invoice.amount,
            currency=invoice.currency,
            due_date=invoice.due_date,
            debtor_id=debtor.id,
            debtor_name=debtor.name,
            debtor_email=debtor.email or None,
            debtor_phone=debtor.phone or None,
        )
        for invoice, debtor in rows
    ]
