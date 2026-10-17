"""Casos de uso: gestión de usuarios de una empresa (lo hace su administrador)."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import BusinessRuleViolationError, ConflictError, NotFoundError
from mavic.modules.identity.application.views import UserView
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import COMPANY_ROLES, Permission, UserRole
from mavic.modules.identity.domain.rules import (
    ensure_company_keeps_an_admin,
    normalize_email,
    validate_new_password,
)
from mavic.modules.identity.infrastructure import passwords
from mavic.modules.identity.infrastructure.orm import UserModel
from mavic.modules.identity.infrastructure.repositories import SessionRepository, UserRepository

EMAIL_TAKEN = "Ya existe un usuario con ese email."


@dataclass(frozen=True)
class UserChanges:
    """Campos que se pueden modificar. None = no se modifica.

    No incluye `company_id` ni `email` a propósito: un usuario no se puede
    "mudar" de empresa, y el email identifica la cuenta.
    """

    name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


def _ensure_company_role(role: UserRole) -> None:
    if role not in COMPANY_ROLES:
        raise BusinessRuleViolationError(
            "Ese rol no se puede asignar a un usuario de empresa.", code="INVALID_ROLE"
        )


def list_users(session: Session, *, actor: Actor) -> list[UserView]:
    actor.require(Permission.MANAGE_USERS)
    users = UserRepository(session).list_by_company(actor.require_company())
    return [UserView.from_model(user) for user in users]


def create_user(
    session: Session, *, actor: Actor, name: str, email: str, password: str, role: UserRole
) -> UserView:
    actor.require(Permission.MANAGE_USERS)
    company_id = actor.require_company()  # el usuario nuevo queda en la empresa del admin
    _ensure_company_role(role)
    validate_new_password(password)

    users = UserRepository(session)
    email = normalize_email(email)
    if users.email_exists(email):
        raise ConflictError(EMAIL_TAKEN, code="EMAIL_ALREADY_REGISTERED")

    user = UserModel(
        company_id=company_id,
        name=name.strip(),
        email=email,
        password_hash=passwords.hash_password(password),
        role=role,
    )
    users.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # Dos altas simultáneas con el mismo email: la restricción UNIQUE de la
        # base frena a la segunda aunque las dos hayan pasado el chequeo de arriba.
        session.rollback()
        raise ConflictError(EMAIL_TAKEN, code="EMAIL_ALREADY_REGISTERED") from exc
    return UserView.from_model(user)


def update_user(
    session: Session, *, actor: Actor, user_id: UUID, changes: UserChanges, clock: Clock
) -> UserView:
    actor.require(Permission.MANAGE_USERS)
    company_id = actor.require_company()

    users = UserRepository(session)
    user = users.get_in_company(user_id, company_id)
    if user is None:
        raise NotFoundError("El usuario no existe.", code="USER_NOT_FOUND")

    if changes.role is not None:
        _ensure_company_role(changes.role)

    new_role = changes.role if changes.role is not None else user.role
    new_active = changes.is_active if changes.is_active is not None else user.is_active
    is_admin_now = user.role == UserRole.ADMIN and user.is_active
    stays_admin = new_role == UserRole.ADMIN and new_active

    if is_admin_now and not stays_admin:
        # Bloquea a los admins activos de la empresa hasta el commit (ver repositorio).
        admins = users.active_admins_for_update(company_id)
        others = [admin for admin in admins if admin.id != user.id]
        ensure_company_keeps_an_admin(other_active_admins=len(others), loses_admin=True)

    if changes.name is not None:
        user.name = changes.name.strip()
    user.role = new_role
    user.is_active = new_active

    if not new_active:
        # Desactivar = cortar el acceso ya, en todos los navegadores.
        SessionRepository(session).revoke_all_for_user(user.id, clock.now())

    session.commit()
    return UserView.from_model(user)
