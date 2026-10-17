"""Casos de uso del dueño de la plataforma: alta de empresas cliente."""

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mavic.core.errors import ConflictError, NotFoundError
from mavic.modules.identity.application.views import CompanyView, UserView
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission, UserRole
from mavic.modules.identity.domain.rules import normalize_email, validate_new_password
from mavic.modules.identity.infrastructure import passwords
from mavic.modules.identity.infrastructure.orm import CompanyModel, UserModel
from mavic.modules.identity.infrastructure.repositories import CompanyRepository, UserRepository


@dataclass(frozen=True)
class NewAdmin:
    name: str
    email: str
    password: str


@dataclass(frozen=True)
class CompanyWithAdmin:
    company: CompanyView
    admin: UserView


def company_name(session: Session, company_id: uuid.UUID) -> str:
    """Nombre de una empresa (sin chequeo de usuario: lo usan otros módulos)."""
    company = CompanyRepository(session).get(company_id)
    if company is None:
        raise NotFoundError("La empresa no existe.", code="COMPANY_NOT_FOUND")
    return company.name


def list_companies(session: Session, *, actor: Actor) -> list[CompanyView]:
    actor.require(Permission.MANAGE_COMPANIES)
    return [CompanyView.from_model(c) for c in CompanyRepository(session).list_all()]


def create_company_with_admin(
    session: Session, *, actor: Actor, name: str, admin: NewAdmin
) -> CompanyWithAdmin:
    """Crea la empresa Y su primer administrador en una sola transacción.

    Si fallara la creación del admin (email repetido, contraseña corta), tampoco
    se crea la empresa: nunca queda una empresa sin nadie que pueda entrar.
    """
    actor.require(Permission.MANAGE_COMPANIES)
    validate_new_password(admin.password)

    companies = CompanyRepository(session)
    users = UserRepository(session)
    name = name.strip()
    email = normalize_email(admin.email)

    if companies.name_exists(name):
        raise ConflictError("Ya existe una empresa con ese nombre.", code="COMPANY_NAME_TAKEN")
    if users.email_exists(email):
        raise ConflictError("Ya existe un usuario con ese email.", code="EMAIL_ALREADY_REGISTERED")

    company = CompanyModel(name=name)
    companies.add(company)
    session.flush()  # manda el INSERT para que la empresa tenga id (sin confirmar todavía)

    user = UserModel(
        company_id=company.id,
        name=admin.name.strip(),
        email=email,
        password_hash=passwords.hash_password(admin.password),
        role=UserRole.ADMIN,
    )
    users.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "La empresa o el email ya existen.", code="COMPANY_OR_EMAIL_TAKEN"
        ) from exc
    return CompanyWithAdmin(
        company=CompanyView.from_model(company), admin=UserView.from_model(user)
    )
