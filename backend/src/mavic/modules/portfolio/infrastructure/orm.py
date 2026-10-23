"""Tablas de la cartera.

    companies 1 ──< debtors 1 ──< cases 1 ──< invoices
                        └───────────────────< invoices (con o sin caso)
    companies 1 ──< invoice_imports (historial de cargas)

AISLAMIENTO ENTRE EMPRESAS EN LA BASE (no solo en el código)
------------------------------------------------------------
En el original se podía crear un caso de la empresa B con un deudor de la
empresa A. Acá eso es IMPOSIBLE a nivel base de datos gracias a claves foráneas
compuestas:

    cases.(debtor_id, company_id)    -> debtors.(id, company_id)
    invoices.(debtor_id, company_id) -> debtors.(id, company_id)
    invoices.(case_id, debtor_id, currency) -> cases.(id, debtor_id, currency)

Traducido: el deudor de un caso tiene que ser de la MISMA empresa que el caso,
y una factura solo puede ir a un caso de SU MISMO deudor y de SU MISMA moneda.
Aunque un bug en el código lo intentara, PostgreSQL rechaza el INSERT.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mavic.core.db import Base, TimestampMixin
from mavic.modules.portfolio.domain.cases import CaseStatus


class DebtorModel(TimestampMixin, Base):
    __tablename__ = "debtors"
    __table_args__ = (
        # El mismo DNI puede ser deudor de dos empresas distintas (en el original
        # el DNI era único en TODO el sistema y una empresa pisaba los datos de otra).
        UniqueConstraint("company_id", "document_number"),
        # Necesaria para que otras tablas apunten a (id, company_id).
        UniqueConstraint("id", "company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    document_number: Mapped[str] = mapped_column(String(11))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))  # formato E.164: +5491122334455
    email: Mapped[str] = mapped_column(String(254))


class CaseModel(TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["debtor_id", "company_id"],
            ["debtors.id", "debtors.company_id"],
            ondelete="RESTRICT",
        ),
        # Para que las facturas apunten a (id, debtor_id, currency): una factura
        # solo entra en un caso de SU deudor y de SU moneda (ADR-034).
        UniqueConstraint("id", "debtor_id", "currency"),
        # Para que otras tablas (llamadas, acuerdos) apunten a (id, company_id).
        UniqueConstraint("id", "company_id"),
        # Un deudor tiene como máximo UN caso pendiente (sin contactar) por
        # moneda. Las facturas que vencen después se suman a ese caso. Es un
        # índice único PARCIAL: solo cuenta las filas con status = 'pending'.
        Index(
            "uq_cases_one_pending_per_debtor_currency",
            "debtor_id",
            "currency",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        Index("ix_cases_company_id_status", "company_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Número legible para personas ("caso 1042"); el id UUID es para el sistema.
    number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    company_id: Mapped[uuid.UUID] = mapped_column()
    debtor_id: Mapped[uuid.UUID] = mapped_column()
    # Un caso agrupa facturas de UNA moneda: nunca se suman pesos con dólares.
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[CaseStatus] = mapped_column(
        Enum(
            CaseStatus,
            name="case_status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=CaseStatus.PENDING,
    )


class InvoiceModel(TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        # El número de factura es único dentro de cada empresa.
        UniqueConstraint("company_id", "external_id"),
        # Para que otras tablas (los avisos) apunten a (id, company_id).
        UniqueConstraint("id", "company_id"),
        ForeignKeyConstraint(
            ["debtor_id", "company_id"],
            ["debtors.id", "debtors.company_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["case_id", "debtor_id", "currency"],
            ["cases.id", "cases.debtor_id", "cases.currency"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        Index("ix_invoices_company_id_case_id", "company_id", "case_id"),
        Index("ix_invoices_debtor_id", "debtor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column()
    debtor_id: Mapped[uuid.UUID] = mapped_column()
    case_id: Mapped[uuid.UUID | None] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    # NUMERIC(14, 2): exacto, hasta 999.999.999.999,99. Nunca float para plata.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date] = mapped_column(Date)


class InvoiceImportModel(Base):
    """Historial de cargas: quién subió qué archivo, cuándo y con qué resultado."""

    __tablename__ = "invoice_imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    filename: Mapped[str] = mapped_column(String(255))
    total_rows: Mapped[int] = mapped_column(Integer)
    debtors_created: Mapped[int] = mapped_column(Integer)
    debtors_updated: Mapped[int] = mapped_column(Integer)
    invoices_created: Mapped[int] = mapped_column(Integer)
    invoices_updated: Mapped[int] = mapped_column(Integer)
    invoices_unchanged: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
