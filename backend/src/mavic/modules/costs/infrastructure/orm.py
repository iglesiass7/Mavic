"""Tabla del medidor de costos: las tarifas de cada empresa (una fila)."""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base, TimestampMixin


class CostRatesModel(TimestampMixin, Base):
    __tablename__ = "cost_rates"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        CheckConstraint(
            "call_minute >= 0 AND email >= 0 AND whatsapp >= 0", name="rates_not_negative"
        ),
        CheckConstraint("monthly_budget IS NULL OR monthly_budget > 0", name="budget_positive"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    # Hasta 4 decimales: un email cuesta fracciones de centavo.
    call_minute: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    email: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    whatsapp: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
