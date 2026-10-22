"""llamadas salientes y moneda del caso (ADR-034)

Revision ID: da8ae5cafd63
Revises: 27bb8094dde0
Create Date: 2026-10-22 20:02:38.318065+00:00

Generada con `alembic revision --autogenerate` y CORREGIDA a mano:

- Las columnas obligatorias nuevas se agregan vacías, se COMPLETAN con los datos
  que ya había y recién después pasan a obligatorias (si no, falla con filas).
- Moneda del caso: se toma de sus facturas. Si un caso viejo tuviera facturas de
  dos monedas, la migración se detiene y lo dice: no se suman monedas distintas
  (hay que separarlo a mano). Hoy no puede pasar: solo se aceptan pesos.
- Conversaciones viejas (flujo con herramientas): origen TOOLS; estado DONE si
  ya llegó su webhook o tiene resultado, IN_PROGRESS si no.
- Acuerdos viejos en cuotas: el importe de cada cuota se toma de la primera
  cuota del cronograma.
- La clave foránea de las facturas se cambia ANTES de borrar la restricción
  única a la que apuntaba. Las restricciones CHECK nuevas las agrega a mano
  (autogenerate no las detecta).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "da8ae5cafd63"
down_revision: str | Sequence[str] | None = "27bb8094dde0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------ bandeja de webhooks
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("provider_conversation_id", sa.String(length=100), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("body_sha256", name=op.f("uq_webhook_events_body_sha256")),
    )
    op.create_index(
        op.f("ix_webhook_events_provider_conversation_id"),
        "webhook_events",
        ["provider_conversation_id"],
        unique=False,
    )

    # ------------------------------------------------------------ moneda del caso
    op.add_column("cases", sa.Column("currency", sa.String(length=3), nullable=True))
    connection = op.get_bind()
    mixed = connection.execute(
        sa.text(
            "SELECT c.number FROM cases c JOIN invoices i ON i.case_id = c.id "
            "GROUP BY c.number HAVING COUNT(DISTINCT i.currency) > 1"
        )
    ).scalars()
    mixed_numbers = list(mixed)
    if mixed_numbers:
        raise RuntimeError(
            f"Casos con facturas de más de una moneda: {mixed_numbers}. "
            "Separalos a mano antes de migrar: no se suman monedas distintas."
        )
    op.execute(
        "UPDATE cases c SET currency = i.currency FROM "
        "(SELECT DISTINCT case_id, currency FROM invoices WHERE case_id IS NOT NULL) i "
        "WHERE i.case_id = c.id"
    )
    op.execute("UPDATE cases SET currency = 'ARS' WHERE currency IS NULL")
    op.alter_column("cases", "currency", existing_type=sa.String(length=3), nullable=False)
    op.create_check_constraint(
        op.f("ck_cases_currency_iso_code"), "cases", "currency ~ '^[A-Z]{3}$'"
    )

    # La factura apunta a (caso, deudor, moneda): primero la restricción nueva,
    # después la clave foránea nueva, y recién ahí se borra lo viejo.
    op.create_unique_constraint(
        op.f("uq_cases_id_debtor_id_currency"), "cases", ["id", "debtor_id", "currency"]
    )
    op.drop_constraint(op.f("fk_invoices_case_id_cases"), "invoices", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_invoices_case_id_cases"),
        "invoices",
        "cases",
        ["case_id", "debtor_id", "currency"],
        ["id", "debtor_id", "currency"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(op.f("uq_cases_id_debtor_id"), "cases", type_="unique")

    # Un caso pendiente por deudor Y moneda.
    op.drop_index(
        op.f("uq_cases_one_pending_per_debtor"),
        table_name="cases",
        postgresql_where="((status)::text = 'pending'::text)",
    )
    op.create_index(
        "uq_cases_one_pending_per_debtor_currency",
        "cases",
        ["debtor_id", "currency"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ------------------------------------------------------------ conversaciones
    for column in (
        sa.Column("provider_call_sid", sa.String(length=64), nullable=True),
        sa.Column("origin", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("branch_id", sa.String(length=100), nullable=True),
        sa.Column("agent_version_id", sa.String(length=100), nullable=True),
        sa.Column("initiation_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.String(length=60), nullable=True),
    ):
        op.add_column("conversations", column)
    op.execute(
        "UPDATE conversations SET origin = 'TOOLS', status = CASE "
        "WHEN webhook_received_at IS NOT NULL OR result IS NOT NULL THEN 'DONE' "
        "ELSE 'IN_PROGRESS' END"
    )
    op.alter_column("conversations", "origin", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("conversations", "status", existing_type=sa.String(length=20), nullable=False)
    op.create_check_constraint(
        op.f("ck_conversations_status_valid"),
        "conversations",
        "status IN ('INITIATING', 'INITIATED', 'IN_PROGRESS', 'DONE', 'FAILED', 'NEEDS_REVIEW')",
    )
    op.create_check_constraint(
        op.f("ck_conversations_origin_valid"),
        "conversations",
        "origin IN ('OUTBOUND', 'TOOLS', 'EXTERNAL')",
    )
    op.alter_column(
        "conversations",
        "provider_conversation_id",
        existing_type=sa.VARCHAR(length=100),
        nullable=True,
    )
    op.create_unique_constraint(
        op.f("uq_conversations_provider_call_sid"), "conversations", ["provider_call_sid"]
    )

    # ------------------------------------------------------------ acuerdos
    op.add_column(
        "payment_agreements",
        sa.Column("installment_amount", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "payment_agreements",
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "payment_agreements",
        sa.Column("discount_amount", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.execute(
        "UPDATE payment_agreements SET installment_amount = (schedule -> 0 ->> 'amount')::numeric "
        "WHERE modality = 'CUOTAS'"
    )
    op.create_check_constraint(
        op.f("ck_payment_agreements_installments_have_amount"),
        "payment_agreements",
        "modality <> 'CUOTAS' OR installment_amount IS NOT NULL",
    )
    op.alter_column(
        "payment_agreements",
        "schedule",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )


def downgrade() -> None:
    # Bajar solo es posible si no hay acuerdos sin cronograma ni llamadas sin id
    # de ElevenLabs (las creadas por el flujo nuevo): la base lo rechaza si los hay.
    op.alter_column(
        "payment_agreements",
        "schedule",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.drop_constraint(
        op.f("ck_payment_agreements_installments_have_amount"), "payment_agreements", type_="check"
    )
    op.drop_column("payment_agreements", "discount_amount")
    op.drop_column("payment_agreements", "discount_pct")
    op.drop_column("payment_agreements", "installment_amount")

    op.drop_constraint(op.f("uq_conversations_provider_call_sid"), "conversations", type_="unique")
    op.alter_column(
        "conversations",
        "provider_conversation_id",
        existing_type=sa.VARCHAR(length=100),
        nullable=False,
    )
    op.drop_constraint(op.f("ck_conversations_origin_valid"), "conversations", type_="check")
    op.drop_constraint(op.f("ck_conversations_status_valid"), "conversations", type_="check")
    for name in (
        "review_reason",
        "failure_reason",
        "initiation_payload",
        "agent_version_id",
        "branch_id",
        "status",
        "origin",
        "provider_call_sid",
    ):
        op.drop_column("conversations", name)

    op.drop_index(
        "uq_cases_one_pending_per_debtor_currency",
        table_name="cases",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        op.f("uq_cases_one_pending_per_debtor"),
        "cases",
        ["debtor_id"],
        unique=True,
        postgresql_where="((status)::text = 'pending'::text)",
    )
    op.create_unique_constraint(op.f("uq_cases_id_debtor_id"), "cases", ["id", "debtor_id"])
    op.drop_constraint(op.f("fk_invoices_case_id_cases"), "invoices", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_invoices_case_id_cases"),
        "invoices",
        "cases",
        ["case_id", "debtor_id"],
        ["id", "debtor_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(op.f("uq_cases_id_debtor_id_currency"), "cases", type_="unique")
    op.drop_constraint(op.f("ck_cases_currency_iso_code"), "cases", type_="check")
    op.drop_column("cases", "currency")

    op.drop_index(op.f("ix_webhook_events_provider_conversation_id"), table_name="webhook_events")
    op.drop_table("webhook_events")
