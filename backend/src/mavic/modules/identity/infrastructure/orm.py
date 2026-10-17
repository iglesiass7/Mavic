"""Tablas de identidad.

    companies 1 ──< users 1 ──< user_sessions

Las restricciones importantes viven en la BASE, no solo en el código: la base
es la única que ve todos los requests a la vez, así que es la última línea de
defensa contra datos inválidos o duplicados.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mavic.core.db import Base, TimestampMixin
from mavic.modules.identity.domain.roles import UserRole


class CompanyModel(TimestampMixin, Base):
    __tablename__ = "companies"

    # UUID en vez de 1, 2, 3...: los ids no se pueden adivinar recorriendo números.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    users: Mapped[list["UserModel"]] = relationship(back_populates="company")


# "FibraSur" y "fibrasur" son la misma empresa: nombre único sin importar mayúsculas.
# Es un índice sobre una expresión (lower(name)), por eso se declara fuera de la clase.
Index("uq_companies_name_lower", func.lower(CompanyModel.name), unique=True)


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # El dueño de la plataforma no tiene empresa; todos los demás, sí.
        CheckConstraint(
            "(role = 'platform_admin') = (company_id IS NULL)",
            name="platform_admin_has_no_company",
        ),
        # El email se guarda ya normalizado: la base rechaza mayúsculas.
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
        Index("ix_users_company_id_role", "company_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        # Se guarda como texto con una restricción CHECK (no como ENUM nativo de
        # PostgreSQL): agregar un rol después es una migración simple.
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda roles: [role.value for role in roles],
        )
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[CompanyModel | None] = relationship(back_populates="users")


class UserSessionModel(Base):
    """Una sesión iniciada (un login). Se guarda en la base para poder revocarla.

    El navegador recibe un token aleatorio en una cookie. En la base se guarda
    solo su hash SHA-256: si alguien robara una copia de la base, no podría usar
    esos valores para entrar.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
