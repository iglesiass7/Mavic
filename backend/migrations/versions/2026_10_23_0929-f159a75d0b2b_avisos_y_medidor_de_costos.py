"""avisos por email y WhatsApp, y medidor de costos (ADR-038 y ADR-039)

Revision ID: f159a75d0b2b
Revises: 767709f01893
Create Date: 2026-10-23 09:29:56.641621+00:00

Generada con `alembic revision --autogenerate` y CORREGIDA a mano:

- La restricción única (id, company_id) de las facturas se crea ANTES que la
  tabla de avisos, que apunta a ella (autogenerate la ponía al final y fallaba).
- No hay datos que copiar: las empresas arrancan con los avisos apagados (la
  configuración de fábrica vive en el código) y sin tarifas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f159a75d0b2b"
down_revision: str | Sequence[str] | None = "767709f01893"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(op.f("uq_invoices_id_company_id"), "invoices", ["id", "company_id"])

    op.create_table(
        "cost_rates",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("call_minute", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("email", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("whatsapp", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("monthly_budget", sa.Numeric(precision=14, scale=2), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_cost_rates_currency_iso_code")),
        sa.CheckConstraint(
            "call_minute >= 0 AND email >= 0 AND whatsapp >= 0",
            name=op.f("ck_cost_rates_rates_not_negative"),
        ),
        sa.CheckConstraint(
            "monthly_budget IS NULL OR monthly_budget > 0",
            name=op.f("ck_cost_rates_budget_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_cost_rates_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", name=op.f("pk_cost_rates")),
    )

    op.create_table(
        "notice_settings",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("send_time", sa.Time(), nullable=False),
        sa.Column("days_before", sa.Integer(), nullable=False),
        sa.Column("email_subject", sa.String(length=150), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("whatsapp_template_sid", sa.String(length=40), nullable=True),
        sa.Column("last_auto_run_on", sa.Date(), nullable=True),
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
            "channel IN ('email', 'whatsapp')", name=op.f("ck_notice_settings_channel_valid")
        ),
        sa.CheckConstraint(
            "stage IN ('preventive', 'due_today')", name=op.f("ck_notice_settings_stage_valid")
        ),
        sa.CheckConstraint(
            "days_before >= 0 AND days_before <= 30",
            name=op.f("ck_notice_settings_days_before_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_notice_settings_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", "stage", name=op.f("pk_notice_settings")),
    )

    op.create_table(
        "notice_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "channel IN ('email', 'whatsapp')", name=op.f("ck_notice_deliveries_channel_valid")
        ),
        sa.CheckConstraint(
            "stage IN ('preventive', 'due_today')", name=op.f("ck_notice_deliveries_stage_valid")
        ),
        sa.CheckConstraint(
            "status IN ('SENDING', 'SENT', 'FAILED')",
            name=op.f("ck_notice_deliveries_status_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('MANUAL', 'AUTOMATIC')", name=op.f("ck_notice_deliveries_trigger_valid")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_notice_deliveries_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id", "company_id"],
            ["invoices.id", "invoices.company_id"],
            name=op.f("fk_notice_deliveries_invoice_id_invoices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_notice_deliveries_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notice_deliveries")),
    )
    op.create_index(
        "ix_notice_deliveries_company_id_created_at",
        "notice_deliveries",
        ["company_id", "created_at"],
        unique=False,
    )
    # Un aviso por factura y momento: los fallidos no cuentan (se pueden reintentar).
    op.create_index(
        "uq_notice_deliveries_one_per_invoice_stage",
        "notice_deliveries",
        ["invoice_id", "stage"],
        unique=True,
        postgresql_where=sa.text("status IN ('SENDING', 'SENT')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notice_deliveries_one_per_invoice_stage",
        table_name="notice_deliveries",
        postgresql_where=sa.text("status IN ('SENDING', 'SENT')"),
    )
    op.drop_index("ix_notice_deliveries_company_id_created_at", table_name="notice_deliveries")
    op.drop_table("notice_deliveries")
    op.drop_table("notice_settings")
    op.drop_table("cost_rates")
    op.drop_constraint(op.f("uq_invoices_id_company_id"), "invoices", type_="unique")
