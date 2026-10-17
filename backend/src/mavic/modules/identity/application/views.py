"""Vistas: lo que los casos de uso devuelven hacia afuera.

¿Por qué no devolver directamente el objeto del ORM (UserModel)? Porque el ORM
trae TODO, incluido `password_hash`. Una vista es una lista explícita de lo que
se puede mostrar: si mañana se agrega una columna sensible a la tabla, no se
filtra sola a la API.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mavic.modules.identity.domain.roles import Permission, UserRole, permissions_for
from mavic.modules.identity.infrastructure.orm import CompanyModel, UserModel


@dataclass(frozen=True)
class CompanyView:
    id: UUID
    name: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, company: CompanyModel) -> "CompanyView":
        return cls(
            id=company.id,
            name=company.name,
            is_active=company.is_active,
            created_at=company.created_at,
        )


@dataclass(frozen=True)
class UserView:
    id: UUID
    company_id: UUID | None
    name: str
    email: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, user: UserModel) -> "UserView":
        return cls(
            id=user.id,
            company_id=user.company_id,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


@dataclass(frozen=True)
class MeView:
    """El usuario que inició sesión, con lo que el frontend necesita para armarse."""

    user: UserView
    company: CompanyView | None
    permissions: frozenset[Permission]

    @classmethod
    def from_model(cls, user: UserModel) -> "MeView":
        return cls(
            user=UserView.from_model(user),
            company=CompanyView.from_model(user.company) if user.company else None,
            permissions=permissions_for(user.role),
        )
