"""auditoría y cuotas de los acuerdos (ADR-036 y ADR-037)

Revision ID: 767709f01893
Revises: da8ae5cafd63
Create Date: 2026-10-23 03:21:09.021116+00:00

Generada con `alembic revision --autogenerate` y CORREGIDA a mano:

- `audit_events` lleva un trigger que impide editar o borrar filas (solo se
  agregan). Autogenerate no ve triggers: se escribe acá.
- La restricción única (id, company_id) de los acuerdos se crea ANTES que la
  tabla de cuotas, que apunta a ella.
- Acuerdos que ya existían: se les arman las cuotas. Si tienen cronograma
  (flujo anterior), con esas fechas; si no, con el plazo de la regla guardado en
  la foto de la llamada, o el de la regla actual, o 5 días.
"""

import calendar
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Copia de lo que hay en audit/infrastructure/orm.py (la migración no importa el
# código de la app: tiene que seguir andando aunque el código cambie).
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events solo admite agregar filas (no se edita ni se borra)';
END;
$$ LANGUAGE plpgsql
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
"""
DEFAULT_PAYMENT_DAYS = 5

revision: str = "767709f01893"
down_revision: str | Sequence[str] | None = "da8ae5cafd63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_kind", sa.String(length=10), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("subject_kind", sa.String(length=20), nullable=True),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("subject_label", sa.String(length=200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_audit_events_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        sa.UniqueConstraint("seq", name=op.f("uq_audit_events_seq")),
    )
    op.create_index(
        "ix_audit_events_company_id_seq", "audit_events", ["company_id", "seq"], unique=False
    )
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)

    op.create_unique_constraint(
        op.f("uq_payment_agreements_id_company_id"), "payment_agreements", ["id", "company_id"]
    )
    op.create_table(
        "agreement_installments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("paid_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_recorded_by", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "(paid_on IS NULL) = (paid_recorded_at IS NULL)",
            name=op.f("ck_agreement_installments_paid_fields_together"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_agreement_installments_amount_positive")),
        sa.CheckConstraint("number >= 1", name=op.f("ck_agreement_installments_number_valid")),
        sa.ForeignKeyConstraint(
            ["agreement_id", "company_id"],
            ["payment_agreements.id", "payment_agreements.company_id"],
            name=op.f("fk_agreement_installments_agreement_id_payment_agreements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_agreement_installments_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paid_recorded_by"],
            ["users.id"],
            name=op.f("fk_agreement_installments_paid_recorded_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement_installments")),
        sa.UniqueConstraint(
            "agreement_id", "number", name=op.f("uq_agreement_installments_agreement_id_number")
        ),
    )
    op.create_index(
        "ix_agreement_installments_company_id_due_date",
        "agreement_installments",
        ["company_id", "due_date"],
        unique=False,
    )
    _installments_for_existing_agreements()


def downgrade() -> None:
    op.drop_index(
        "ix_agreement_installments_company_id_due_date", table_name="agreement_installments"
    )
    op.drop_table("agreement_installments")
    op.drop_constraint(
        op.f("uq_payment_agreements_id_company_id"), "payment_agreements", type_="unique"
    )
    op.drop_index("ix_audit_events_company_id_seq", table_name="audit_events")
    op.drop_table("audit_events")  # se lleva el trigger
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _installments_for_existing_agreements() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT a.id, a.company_id, a.installment_count, a.installment_amount,
                   a.total_amount, a.schedule,
                   (a.created_at AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS agreed_on,
                   c.initiation_payload -> 'rule' ->> 'payment_days' AS snapshot_days,
                   r.payment_days AS rule_days
            FROM payment_agreements a
            JOIN conversations c ON c.id = a.conversation_id
            LEFT JOIN negotiation_rules r
                   ON r.id::text = c.initiation_payload -> 'rule' ->> 'id'
            """
        )
    ).mappings()
    insert = sa.text(
        "INSERT INTO agreement_installments"
        " (id, company_id, agreement_id, number, due_date, amount)"
        " VALUES (:id, :company_id, :agreement_id, :number, :due_date, :amount)"
    )
    for row in rows:
        if row["schedule"]:
            lines = [
                (
                    int(x["number"]),
                    date.fromisoformat(str(x["due_date"])),
                    Decimal(str(x["amount"])),
                )
                for x in row["schedule"]
            ]
        else:
            days = row["snapshot_days"] or row["rule_days"] or DEFAULT_PAYMENT_DAYS
            first = row["agreed_on"] + timedelta(days=int(days))
            each = row["installment_amount"] or row["total_amount"]
            lines = [
                (n, _add_months(first, n - 1), each)
                for n in range(1, int(row["installment_count"]) + 1)
            ]
        for number, due_date, amount in lines:
            bind.execute(
                insert,
                {
                    "id": uuid.uuid4(),
                    "company_id": row["company_id"],
                    "agreement_id": row["id"],
                    "number": number,
                    "due_date": due_date,
                    "amount": amount,
                },
            )
