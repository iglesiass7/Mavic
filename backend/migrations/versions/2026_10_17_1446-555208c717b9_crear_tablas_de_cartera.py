"""crear tablas de cartera

Revision ID: 555208c717b9
Revises: 6b2e237a421a
Create Date: 2026-10-17 14:46:10.496538+00:00

Generada con `alembic revision --autogenerate` y revisada a mano: se sacó la
restricción CHECK duplicada de los estados del caso (la del Enum y la explícita).

Las claves foráneas compuestas impiden mezclar datos de empresas distintas:
ver el comentario de mavic/modules/portfolio/infrastructure/orm.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "555208c717b9"
down_revision: str | Sequence[str] | None = "6b2e237a421a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CASE_STATUSES = ("pending", "contacted", "agreement", "disputed", "escalated", "closed")


def upgrade() -> None:
    op.create_table(
        "debtors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("document_number", sa.String(length=11), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_debtors_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_debtors")),
        sa.UniqueConstraint(
            "company_id", "document_number", name=op.f("uq_debtors_company_id_document_number")
        ),
        sa.UniqueConstraint("id", "company_id", name=op.f("uq_debtors_id_company_id")),
    )
    op.create_index(op.f("ix_debtors_company_id"), "debtors", ["company_id"], unique=False)
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("debtor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*CASE_STATUSES, name="case_status", native_enum=False, length=20),
            nullable=False,
        ),
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
            "status IN ('pending', 'contacted', 'agreement', 'disputed', 'escalated', 'closed')",
            name=op.f("ck_cases_case_status"),
        ),
        sa.ForeignKeyConstraint(
            ["debtor_id", "company_id"],
            ["debtors.id", "debtors.company_id"],
            name=op.f("fk_cases_debtor_id_debtors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint("id", "debtor_id", name=op.f("uq_cases_id_debtor_id")),
        sa.UniqueConstraint("number", name=op.f("uq_cases_number")),
    )
    op.create_index("ix_cases_company_id_status", "cases", ["company_id", "status"], unique=False)
    op.create_index(
        "uq_cases_one_pending_per_debtor",
        "cases",
        ["debtor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "invoice_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("debtors_created", sa.Integer(), nullable=False),
        sa.Column("debtors_updated", sa.Integer(), nullable=False),
        sa.Column("invoices_created", sa.Integer(), nullable=False),
        sa.Column("invoices_updated", sa.Integer(), nullable=False),
        sa.Column("invoices_unchanged", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_invoice_imports_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_invoice_imports_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_imports")),
    )
    op.create_index(
        op.f("ix_invoice_imports_company_id"), "invoice_imports", ["company_id"], unique=False
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("debtor_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_invoices_currency_iso_code")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_invoices_amount_positive")),
        sa.ForeignKeyConstraint(
            ["case_id", "debtor_id"],
            ["cases.id", "cases.debtor_id"],
            name=op.f("fk_invoices_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["debtor_id", "company_id"],
            ["debtors.id", "debtors.company_id"],
            name=op.f("fk_invoices_debtor_id_debtors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint(
            "company_id", "external_id", name=op.f("uq_invoices_company_id_external_id")
        ),
    )
    op.create_index(
        "ix_invoices_company_id_case_id", "invoices", ["company_id", "case_id"], unique=False
    )
    op.create_index("ix_invoices_debtor_id", "invoices", ["debtor_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invoices_debtor_id", table_name="invoices")
    op.drop_index("ix_invoices_company_id_case_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_invoice_imports_company_id"), table_name="invoice_imports")
    op.drop_table("invoice_imports")
    op.drop_index(
        "uq_cases_one_pending_per_debtor",
        table_name="cases",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index("ix_cases_company_id_status", table_name="cases")
    op.drop_table("cases")
    op.drop_index(op.f("ix_debtors_company_id"), table_name="debtors")
    op.drop_table("debtors")
