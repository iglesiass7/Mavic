"""Tabla de reglas de negociación.

Cada regla es de UNA empresa. Los rangos se guardan como dos columnas
(mínimo y máximo); un máximo NULL significa "sin tope".

La base repite las validaciones del dominio con restricciones CHECK: aunque un
script o un bug intentara guardar un descuento de 150 %, PostgreSQL lo rechaza.
"""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base, TimestampMixin
from mavic.modules.negotiation.domain.rules import MAX_INSTALLMENTS, MAX_PAYMENT_DAYS


def _range_checks(column: str, lowest: int) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(f"min_{column} >= {lowest}", name=f"{column}_min_valid"),
        CheckConstraint(
            f"max_{column} IS NULL OR max_{column} >= min_{column}", name=f"{column}_range_valid"
        ),
    )


class NegotiationRuleModel(TimestampMixin, Base):
    __tablename__ = "negotiation_rules"
    __table_args__ = (
        *_range_checks("amount", 0),
        *_range_checks("debt_age_days", 0),
        *_range_checks("invoice_count", 1),
        CheckConstraint("discount_pct >= 0 AND discount_pct < 100", name="discount_pct_valid"),
        CheckConstraint("interest_pct >= 0 AND interest_pct <= 100", name="interest_pct_valid"),
        CheckConstraint(
            f"max_installments BETWEEN 1 AND {MAX_INSTALLMENTS}", name="max_installments_valid"
        ),
        CheckConstraint(
            f"payment_days BETWEEN 1 AND {MAX_PAYMENT_DAYS}", name="payment_days_valid"
        ),
        Index("ix_negotiation_rules_company_id_is_active", "company_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="")

    # Condiciones: a qué casos se aplica.
    min_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_debt_age_days: Mapped[int] = mapped_column(Integer)
    max_debt_age_days: Mapped[int | None] = mapped_column(Integer)
    min_invoice_count: Mapped[int] = mapped_column(Integer)
    max_invoice_count: Mapped[int | None] = mapped_column(Integer)

    # Condiciones de pago: qué se puede ofrecer.
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    payment_days: Mapped[int] = mapped_column(Integer)
    max_installments: Mapped[int] = mapped_column(Integer)
    interest_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    # Una regla desactivada no se aplica, pero se conserva (historial, reactivarla).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# Dos reglas de la misma empresa no pueden llamarse igual ("Mora alta" = "mora alta").
Index(
    "uq_negotiation_rules_company_id_name_lower",
    NegotiationRuleModel.company_id,
    func.lower(NegotiationRuleModel.name),
    unique=True,
)
