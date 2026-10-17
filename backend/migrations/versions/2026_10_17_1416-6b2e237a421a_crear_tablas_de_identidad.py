"""crear tablas de identidad: empresas, usuarios y sesiones

Revision ID: 6b2e237a421a
Revises:
Create Date: 2026-10-17 14:16:18+00:00

Generada con `alembic revision --autogenerate` y revisada a mano: Alembic
duplicaba la restricción CHECK de los roles (una por el Enum y otra explícita).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b2e237a421a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("admin", "operator", "supervisor", "platform_admin")


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    # Nombre de empresa único sin distinguir mayúsculas.
    op.create_index(
        "uq_companies_name_lower", "companies", [sa.literal_column("lower(name)")], unique=True
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            # La restricción de valores se crea explícita más abajo (una sola vez).
            sa.Enum(*ROLES, name="user_role", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
            "role IN ('admin', 'operator', 'supervisor', 'platform_admin')",
            name=op.f("ck_users_user_role"),
        ),
        sa.CheckConstraint(
            "(role = 'platform_admin') = (company_id IS NULL)",
            name=op.f("ck_users_platform_admin_has_no_company"),
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_is_lowercase")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_users_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index("ix_users_company_id_role", "users", ["company_id", "role"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    # Orden inverso: primero lo que depende de otras tablas.
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_users_company_id_role", table_name="users")
    op.drop_table("users")
    op.drop_index("uq_companies_name_lower", table_name="companies")
    op.drop_table("companies")
