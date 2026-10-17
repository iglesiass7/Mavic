"""Ayudantes para armar datos de prueba.

Crean los datos con los MISMOS casos de uso que usa la app (no con INSERTs
directos), así los datos de prueba respetan las mismas reglas que los reales.
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mavic.core.db import Database
from mavic.modules.identity.application import bootstrap, companies, users
from mavic.modules.identity.application.companies import CompanyWithAdmin
from mavic.modules.identity.application.views import UserView
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import UserRole

PASSWORD = "clave-de-prueba-123"

# Un actor "dueño de la plataforma" para crear empresas en los tests. El caso de
# uso solo mira su rol, así que el id puede ser cualquiera.
PLATFORM_ACTOR = Actor(user_id=uuid.uuid4(), company_id=None, role=UserRole.PLATFORM_ADMIN)


def make_company(
    database: Database, name: str = "FibraSur", admin_email: str | None = None
) -> CompanyWithAdmin:
    admin_email = admin_email or f"admin@{name.lower().replace(' ', '')}.com"
    with database.session() as session:
        return companies.create_company_with_admin(
            session,
            actor=PLATFORM_ACTOR,
            name=name,
            admin=companies.NewAdmin(name="Admin", email=admin_email, password=PASSWORD),
        )


def make_user(
    database: Database, company: CompanyWithAdmin, email: str, role: UserRole
) -> UserView:
    admin = Actor(user_id=company.admin.id, company_id=company.company.id, role=UserRole.ADMIN)
    with database.session() as session:
        return users.create_user(
            session,
            actor=admin,
            name=email.split("@")[0],
            email=email,
            password=PASSWORD,
            role=role,
        )


def make_platform_admin(database: Database, email: str = "dueno@mavic-demo.com") -> UserView:
    with database.session() as session:
        return bootstrap.create_platform_admin(
            session, name="Dueño", email=email, password=PASSWORD
        )


def logged_client(app: FastAPI, email: str, password: str = PASSWORD) -> TestClient:
    """Un cliente HTTP nuevo, con la sesión iniciada (guarda su propia cookie)."""
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client
