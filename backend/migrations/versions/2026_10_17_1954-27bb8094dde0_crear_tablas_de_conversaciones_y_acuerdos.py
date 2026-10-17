"""crear tablas de conversaciones y acuerdos de pago

Revision ID: 27bb8094dde0
Revises: 23e2fa04c9ee
Create Date: 2026-10-17 19:54:20.481780+00:00

Generada con `alembic revision --autogenerate` y CORREGIDA a mano: Alembic
creaba la restricción única de `cases (id, company_id)` al final, pero las
claves foráneas de las tablas nuevas la necesitan desde el principio. Y al
bajar la borraba primero, antes que las tablas que dependen de ella.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "27bb8094dde0"
down_revision: str | Sequence[str] | None = "23e2fa04c9ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Primero: las claves foráneas compuestas de abajo apuntan a esta restricción.
    op.create_unique_constraint(op.f("uq_cases_id_company_id"), "cases", ["id", "company_id"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("provider_conversation_id", sa.String(length=100), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("offers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("single_payment_offered", sa.Boolean(), nullable=False),
        sa.Column("installments_offered", sa.Boolean(), nullable=False),
        sa.Column("result", sa.String(length=30), nullable=True),
        sa.Column("accepted_offer_id", sa.String(length=40), nullable=True),
        sa.Column("final_confirmation", sa.Boolean(), nullable=True),
        sa.Column("unknown_count", sa.Integer(), nullable=True),
        sa.Column("result_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("call_duration_secs", sa.Integer(), nullable=True),
        sa.Column("termination_reason", sa.String(length=200), nullable=True),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("webhook_received_at", sa.DateTime(timezone=True), nullable=True),
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
            "result IS NULL OR result IN "
            "('CONTACTADO', 'DESCONOCIMIENTO', 'ACUERDO', 'DERIVACION_HUMANA')",
            name=op.f("ck_conversations_result_valid"),
        ),
        sa.CheckConstraint(
            "unknown_count IS NULL OR unknown_count >= 0",
            name=op.f("ck_conversations_unknown_count_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["cases.id", "cases.company_id"],
            name=op.f("fk_conversations_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_conversations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint(
            "provider_conversation_id", name=op.f("uq_conversations_provider_conversation_id")
        ),
    )
    op.create_index("ix_conversations_case_id", "conversations", ["case_id"], unique=False)
    op.create_table(
        "payment_agreements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.String(length=40), nullable=False),
        sa.Column("modality", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("original_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("installment_count", sa.Integer(), nullable=False),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "modality IN ('PAGO_UNICO', 'CUOTAS')",
            name=op.f("ck_payment_agreements_modality_valid"),
        ),
        sa.CheckConstraint(
            "installment_count >= 1", name=op.f("ck_payment_agreements_installment_count_valid")
        ),
        sa.CheckConstraint(
            "total_amount > 0", name=op.f("ck_payment_agreements_total_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["cases.id", "cases.company_id"],
            name=op.f("fk_payment_agreements_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_payment_agreements_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_payment_agreements_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_agreements")),
        sa.UniqueConstraint("conversation_id", name=op.f("uq_payment_agreements_conversation_id")),
    )
    op.create_index(
        "ix_payment_agreements_case_id", "payment_agreements", ["case_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_payment_agreements_case_id", table_name="payment_agreements")
    op.drop_table("payment_agreements")
    op.drop_index("ix_conversations_case_id", table_name="conversations")
    op.drop_table("conversations")
    # Último: ya no queda ninguna clave foránea que la use.
    op.drop_constraint(op.f("uq_cases_id_company_id"), "cases", type_="unique")
