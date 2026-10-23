import uuid

import pytest

from mavic.core.errors import PermissionDeniedError
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission, UserRole, permissions_for


def test_admin_manages_users_and_rules() -> None:
    perms = permissions_for(UserRole.ADMIN)
    assert Permission.MANAGE_USERS in perms
    assert Permission.MANAGE_RULES in perms


def test_operator_works_the_portfolio_but_does_not_manage() -> None:
    perms = permissions_for(UserRole.OPERATOR)
    assert Permission.OPERATE_PORTFOLIO in perms
    assert Permission.MANAGE_USERS not in perms
    assert Permission.MANAGE_RULES not in perms


def test_supervisor_can_only_view() -> None:
    # Ve la cartera, la auditoría y los costos, pero no cambia nada.
    assert permissions_for(UserRole.SUPERVISOR) == {
        Permission.VIEW_PORTFOLIO,
        Permission.VIEW_AUDIT,
        Permission.VIEW_COSTS,
    }


def test_only_the_admin_changes_cost_rates() -> None:
    holders = {role for role in UserRole if Permission.MANAGE_COSTS in permissions_for(role)}
    assert holders == {UserRole.ADMIN}


def test_platform_admin_does_not_see_company_portfolio() -> None:
    # Privacidad: el dueño de la plataforma crea empresas, no mira deudores ajenos.
    assert permissions_for(UserRole.PLATFORM_ADMIN) == {Permission.MANAGE_COMPANIES}


def test_every_role_has_permissions_defined() -> None:
    for role in UserRole:
        assert permissions_for(role), f"El rol {role} no tiene permisos definidos"


def test_actor_require_raises_without_permission() -> None:
    supervisor = Actor(user_id=uuid.uuid4(), company_id=uuid.uuid4(), role=UserRole.SUPERVISOR)
    with pytest.raises(PermissionDeniedError):
        supervisor.require(Permission.MANAGE_USERS)


def test_require_company_rejects_platform_admin() -> None:
    owner = Actor(user_id=uuid.uuid4(), company_id=None, role=UserRole.PLATFORM_ADMIN)
    with pytest.raises(PermissionDeniedError):
        owner.require_company()
