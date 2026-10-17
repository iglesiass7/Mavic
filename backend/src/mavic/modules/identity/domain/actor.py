"""El "actor": quién está haciendo la operación.

Cada caso de uso recibe un Actor (no un request HTTP). Así la autorización vive
en la capa de aplicación y vale igual si el caso de uso se llama desde la API,
desde un comando de consola o desde un test.

    request HTTP --cookie--> sesión --> Actor(user, empresa, rol) --> caso de uso
                                                                     actor.require(...)
"""

from dataclasses import dataclass
from uuid import UUID

from mavic.core.errors import PermissionDeniedError
from mavic.modules.identity.domain.roles import Permission, UserRole, permissions_for


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    company_id: UUID | None  # None solo para el dueño de la plataforma
    role: UserRole

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        """Corta la operación si el actor no tiene el permiso."""
        if not self.can(permission):
            raise PermissionDeniedError()

    def require_company(self) -> UUID:
        """Empresa del actor. Todo dato de negocio se filtra por este valor.

        Es la regla que evita que una empresa vea datos de otra: el id de la
        empresa sale SIEMPRE de la sesión, nunca de lo que manda el cliente.
        """
        if self.company_id is None:
            raise PermissionDeniedError("Esta operación es solo para usuarios de una empresa.")
        return self.company_id
