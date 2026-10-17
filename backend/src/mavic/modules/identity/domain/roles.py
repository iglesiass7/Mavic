"""Roles y permisos.

Idea central: el código NUNCA pregunta "¿es admin?". Pregunta "¿tiene el permiso
X?". Un rol es solo un paquete de permisos con nombre.

    usuario --tiene--> rol --incluye--> permisos
    Laura   --------> ADMIN ----------> {VIEW_PORTFOLIO, OPERATE_PORTFOLIO, MANAGE_RULES, ...}

Ventaja (principio abierto/cerrado): para agregar un rol nuevo se agrega una
entrada en ROLE_PERMISSIONS y no se toca ningún endpoint ni caso de uso.
"""

from enum import StrEnum


class UserRole(StrEnum):
    # Usuarios de una empresa cliente
    ADMIN = "admin"  # jefe de cobranzas: usuarios y reglas
    OPERATOR = "operator"  # analista: trabajo diario con la cartera
    SUPERVISOR = "supervisor"  # gerencia: solo lectura

    # Dueño de la plataforma: crea empresas cliente. No pertenece a ninguna
    # empresa y, a propósito, NO ve los datos de deudores de las empresas.
    PLATFORM_ADMIN = "platform_admin"


# Roles que un administrador de empresa puede asignar a sus usuarios.
COMPANY_ROLES = frozenset({UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPERVISOR})


class Permission(StrEnum):
    VIEW_PORTFOLIO = "view_portfolio"  # ver casos, facturas, conversaciones, tablero
    OPERATE_PORTFOLIO = "operate_portfolio"  # importar, crear casos, contactar, derivaciones
    MANAGE_RULES = "manage_rules"  # reglas de negociación
    MANAGE_USERS = "manage_users"  # usuarios de la propia empresa
    MANAGE_COMPANIES = "manage_companies"  # empresas cliente (solo plataforma)


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: frozenset(
        {
            Permission.VIEW_PORTFOLIO,
            Permission.OPERATE_PORTFOLIO,
            Permission.MANAGE_RULES,
            Permission.MANAGE_USERS,
        }
    ),
    UserRole.OPERATOR: frozenset({Permission.VIEW_PORTFOLIO, Permission.OPERATE_PORTFOLIO}),
    UserRole.SUPERVISOR: frozenset({Permission.VIEW_PORTFOLIO}),
    UserRole.PLATFORM_ADMIN: frozenset({Permission.MANAGE_COMPANIES}),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
