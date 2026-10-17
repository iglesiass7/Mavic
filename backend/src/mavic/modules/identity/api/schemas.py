"""Contratos de la API: qué se recibe y qué se devuelve.

`extra="forbid"` en las entradas: si el cliente manda un campo que no existe
(por ejemplo `company_id` al editar un usuario), la API responde 422 en vez de
ignorarlo en silencio. En el original, ese campo se aceptaba y permitía mover un
usuario a otra empresa.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from mavic.modules.identity.application.views import CompanyView, MeView, UserView
from mavic.modules.identity.domain.roles import Permission, UserRole

# Texto con espacios recortados y largo controlado.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
# El largo mínimo de la contraseña lo valida el dominio (regla de negocio, con
# su propio código de error). Acá solo se pone un tope para no procesar textos enormes.
Password = Annotated[str, Field(max_length=128)]
# Roles que se pueden asignar desde la API (nunca platform_admin).
CompanyRole = Literal["admin", "operator", "supervisor"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- entradas


class LoginIn(InputModel):
    # En el login el email NO se valida como "email bien formado", solo se
    # limita el largo. Si la validación cambiara (por ejemplo, una versión nueva
    # de la librería que rechace un dominio), nadie debería quedar sin poder
    # entrar a una cuenta que ya existe. El formato se valida al CREAR usuarios.
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]
    password: Password


class PasswordChangeIn(InputModel):
    current_password: Password
    new_password: Password


class UserCreateIn(InputModel):
    name: Name
    email: EmailStr
    password: Password
    role: CompanyRole


class UserUpdateIn(InputModel):
    name: Name | None = None
    role: CompanyRole | None = None
    is_active: bool | None = None


class AdminIn(InputModel):
    name: Name
    email: EmailStr
    password: Password


class CompanyCreateIn(InputModel):
    name: Name
    admin: AdminIn


# ---------------------------------------------------------------- salidas


class CompanyOut(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_view(cls, view: CompanyView) -> "CompanyOut":
        return cls(id=view.id, name=view.name, is_active=view.is_active, created_at=view.created_at)


class UserOut(BaseModel):
    id: UUID
    company_id: UUID | None
    name: str
    email: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    @classmethod
    def from_view(cls, view: UserView) -> "UserOut":
        return cls(
            id=view.id,
            company_id=view.company_id,
            name=view.name,
            email=view.email,
            role=view.role,
            is_active=view.is_active,
            last_login_at=view.last_login_at,
            created_at=view.created_at,
        )


class MeOut(BaseModel):
    user: UserOut
    company: CompanyOut | None
    # El frontend usa esta lista para mostrar u ocultar botones. Ocultar un botón
    # es comodidad, NO seguridad: el backend vuelve a validar el permiso siempre.
    permissions: list[Permission]

    @classmethod
    def from_view(cls, view: MeView) -> "MeOut":
        return cls(
            user=UserOut.from_view(view.user),
            company=CompanyOut.from_view(view.company) if view.company else None,
            permissions=sorted(view.permissions),
        )


class CompanyWithAdminOut(BaseModel):
    company: CompanyOut
    admin: UserOut
