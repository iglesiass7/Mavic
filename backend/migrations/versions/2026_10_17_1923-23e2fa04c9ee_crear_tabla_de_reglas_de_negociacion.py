"""crear tabla de reglas de negociación

Revision ID: 23e2fa04c9ee
Revises: 555208c717b9
Create Date: 2026-10-17 19:23:20.963558+00:00

Generada con `alembic revision --autogenerate` y revisada a mano.

Los límites de las restricciones CHECK (36 cuotas, 90 días) quedan escritos
como números: una migración es una foto del esquema en este momento. Si mañana
cambian los límites, se hace una migración nueva.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "23e2fa04c9ee"
down_revision: str | Sequence[str] | None = "555208c717b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "negotiation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("min_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("max_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("min_debt_age_days", sa.Integer(), nullable=False),
        sa.Column("max_debt_age_days", sa.Integer(), nullable=True),
        sa.Column("min_invoice_count", sa.Integer(), nullable=False),
        sa.Column("max_invoice_count", sa.Integer(), nullable=True),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("payment_days", sa.Integer(), nullable=False),
        sa.Column("max_installments", sa.Integer(), nullable=False),
        sa.Column("interest_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "discount_pct >= 0 AND discount_pct < 100",
            name=op.f("ck_negotiation_rules_discount_pct_valid"),
        ),
        sa.CheckConstraint(
            "interest_pct >= 0 AND interest_pct <= 100",
            name=op.f("ck_negotiation_rules_interest_pct_valid"),
        ),
        sa.CheckConstraint(
            "max_amount IS NULL OR max_amount >= min_amount",
            name=op.f("ck_negotiation_rules_amount_range_valid"),
        ),
        sa.CheckConstraint(
            "max_debt_age_days IS NULL OR max_debt_age_days >= min_debt_age_days",
            name=op.f("ck_negotiation_rules_debt_age_days_range_valid"),
        ),
        sa.CheckConstraint(
            "max_installments BETWEEN 1 AND 36",
            name=op.f("ck_negotiation_rules_max_installments_valid"),
        ),
        sa.CheckConstraint(
            "max_invoice_count IS NULL OR max_invoice_count >= min_invoice_count",
            name=op.f("ck_negotiation_rules_invoice_count_range_valid"),
        ),
        sa.CheckConstraint("min_amount >= 0", name=op.f("ck_negotiation_rules_amount_min_valid")),
        sa.CheckConstraint(
            "min_debt_age_days >= 0", name=op.f("ck_negotiation_rules_debt_age_days_min_valid")
        ),
        sa.CheckConstraint(
            "min_invoice_count >= 1", name=op.f("ck_negotiation_rules_invoice_count_min_valid")
        ),
        sa.CheckConstraint(
            "payment_days BETWEEN 1 AND 90", name=op.f("ck_negotiation_rules_payment_days_valid")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_negotiation_rules_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_negotiation_rules")),
    )
    op.create_index(
        "ix_negotiation_rules_company_id_is_active",
        "negotiation_rules",
        ["company_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "uq_negotiation_rules_company_id_name_lower",
        "negotiation_rules",
        ["company_id", sa.literal_column("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_negotiation_rules_company_id_name_lower", table_name="negotiation_rules")
    op.drop_index("ix_negotiation_rules_company_id_is_active", table_name="negotiation_rules")
    op.drop_table("negotiation_rules")
