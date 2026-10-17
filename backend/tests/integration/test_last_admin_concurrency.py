"""Concurrencia: dos administradores se desactivan mutuamente AL MISMO TIEMPO.

Sin bloqueo, la carrera sería:

    request A: "¿quedan otros admins además de Ana?" -> sí, Beto   -> desactiva a Ana
    request B: "¿quedan otros admins además de Beto?" -> sí, Ana   -> desactiva a Beto
    resultado: la empresa se queda sin administradores

Con `SELECT ... FOR UPDATE`, el segundo request espera a que el primero termine
y recién ahí cuenta: ve que ya no queda nadie y se rechaza.

El test lanza los dos casos de uso en hilos distintos, con sesiones de base
distintas (como dos requests reales), y verifica que exactamente uno gana.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from mavic.core.clock import FixedClock
from mavic.core.db import Database
from mavic.core.errors import ConflictError
from mavic.modules.identity.application import users
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.identity.infrastructure.orm import UserModel
from tests.factories import make_company, make_user

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def test_two_admins_cannot_deactivate_each_other_at_the_same_time(database: Database) -> None:
    company = make_company(database, admin_email="ana@fibrasur.com")
    beto = make_user(database, company, "beto@fibrasur.com", UserRole.ADMIN)
    company_id = company.company.id
    ana_id = company.admin.id
    clock = FixedClock(datetime(2026, 10, 16, 15, 0, tzinfo=UTC), "America/Argentina/Buenos_Aires")

    start = threading.Barrier(2)  # los dos hilos arrancan juntos
    results: list[str] = []

    def deactivate(actor_id: uuid.UUID, target_id: uuid.UUID) -> None:
        actor = Actor(user_id=actor_id, company_id=company_id, role=UserRole.ADMIN)
        with database.session() as session:
            start.wait()
            try:
                users.update_user(
                    session,
                    actor=actor,
                    user_id=target_id,
                    changes=users.UserChanges(is_active=False),
                    clock=clock,
                )
                results.append("ok")
            except ConflictError:
                results.append("rechazado")

    threads = [
        threading.Thread(target=deactivate, args=(ana_id, beto.id)),
        threading.Thread(target=deactivate, args=(beto.id, ana_id)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results) == ["ok", "rechazado"]
    with database.session() as session:
        active_admins = session.scalar(
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.company_id == company_id,
                UserModel.role == UserRole.ADMIN,
                UserModel.is_active.is_(True),
            )
        )
    assert active_admins == 1
