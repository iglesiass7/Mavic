"""Repositorios: las consultas a la base de identidad, en un solo lugar.

Un repositorio esconde el "cómo" (SQL, joins, bloqueos) detrás de métodos con
nombre de negocio: `users.active_admins_for_update(company_id)` se lee mejor que
una consulta SQLAlchemy en medio de un caso de uso.

Regla: los repositorios NUNCA hacen commit. Agregan, modifican y como mucho
hacen `flush()` (mandar los cambios a la base sin confirmarlos). El commit es
decisión del caso de uso.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.identity.infrastructure.orm import CompanyModel, UserModel, UserSessionModel


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, company: CompanyModel) -> None:
        self._session.add(company)

    def get(self, company_id: uuid.UUID) -> CompanyModel | None:
        return self._session.get(CompanyModel, company_id)

    def name_exists(self, name: str) -> bool:
        query = select(CompanyModel.id).where(func.lower(CompanyModel.name) == name.lower())
        return self._session.scalar(query) is not None

    def list_all(self) -> list[CompanyModel]:
        return list(self._session.scalars(select(CompanyModel).order_by(CompanyModel.name)))


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: UserModel) -> None:
        self._session.add(user)

    def get(self, user_id: uuid.UUID) -> UserModel | None:
        return self._session.get(UserModel, user_id)

    def get_in_company(self, user_id: uuid.UUID, company_id: uuid.UUID) -> UserModel | None:
        """Busca el usuario SOLO dentro de la empresa indicada.

        Si existe pero es de otra empresa, devuelve None: para el que pregunta
        es como si no existiera (no revelamos datos de otras empresas).
        """
        query = select(UserModel).where(UserModel.id == user_id, UserModel.company_id == company_id)
        return self._session.scalar(query)

    def get_by_email(self, email: str) -> UserModel | None:
        return self._session.scalar(select(UserModel).where(UserModel.email == email))

    def email_exists(self, email: str) -> bool:
        return (
            self._session.scalar(select(UserModel.id).where(UserModel.email == email)) is not None
        )

    def list_by_company(self, company_id: uuid.UUID) -> list[UserModel]:
        query = select(UserModel).where(UserModel.company_id == company_id).order_by(UserModel.name)
        return list(self._session.scalars(query))

    def active_admins_for_update(self, company_id: uuid.UUID) -> list[UserModel]:
        """Administradores activos de la empresa, BLOQUEADOS hasta el commit.

        `SELECT ... FOR UPDATE` bloquea esas filas: si otro request intenta lo
        mismo al mismo tiempo, espera a que este termine. Sin el bloqueo, dos
        admins podrían desactivarse mutuamente a la vez y la empresa quedaría
        sin ninguno (cada request "veía" al otro todavía activo).
        """
        query = (
            select(UserModel)
            .where(
                UserModel.company_id == company_id,
                UserModel.role == UserRole.ADMIN,
                UserModel.is_active.is_(True),
            )
            .order_by(UserModel.id)  # orden fijo: evita interbloqueos (deadlocks)
            .with_for_update()
            # Si alguno de estos usuarios ya estaba cargado en memoria, se lo
            # actualiza con lo que hay en la base DESPUÉS de obtener el bloqueo.
            .execution_options(populate_existing=True)
        )
        return list(self._session.scalars(query))


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user_session: UserSessionModel) -> None:
        self._session.add(user_session)

    def get_valid_by_token_hash(
        self, token_hash: str, now: datetime
    ) -> tuple[UserSessionModel, UserModel] | None:
        """Sesión vigente (no revocada ni vencida) junto con su usuario."""
        query = (
            select(UserSessionModel, UserModel)
            .join(UserModel, UserModel.id == UserSessionModel.user_id)
            .where(
                UserSessionModel.token_hash == token_hash,
                UserSessionModel.revoked_at.is_(None),
                UserSessionModel.expires_at > now,
            )
        )
        row = self._session.execute(query).first()
        return None if row is None else (row[0], row[1])

    def get_by_token_hash(self, token_hash: str) -> UserSessionModel | None:
        query = select(UserSessionModel).where(UserSessionModel.token_hash == token_hash)
        return self._session.scalar(query)

    def revoke_all_for_user(
        self, user_id: uuid.UUID, now: datetime, *, except_id: uuid.UUID | None = None
    ) -> None:
        query = update(UserSessionModel).where(
            UserSessionModel.user_id == user_id, UserSessionModel.revoked_at.is_(None)
        )
        if except_id is not None:
            query = query.where(UserSessionModel.id != except_id)
        self._session.execute(query.values(revoked_at=now))
