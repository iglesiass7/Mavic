r"""Comandos de consola para administrar Mavic.

Con Docker (lo habitual):

    docker compose exec backend python -m mavic.cli create-platform-admin \
        --name "Mateo" --email yo@mavic-demo.com
    docker compose exec backend python -m mavic.cli seed-demo

- create-platform-admin: crea al dueño de la plataforma. Pide la contraseña sin
  mostrarla en pantalla (y sin que quede en el historial de la consola).
- seed-demo: crea datos de ejemplo para probar la app (empresa, usuarios y
  reglas de negociación). Solo en APP_ENV=local.
"""

import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from mavic.core.config import get_settings
from mavic.core.db import Database
from mavic.core.errors import AppError
from mavic.modules.identity.application import bootstrap, companies, users
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.identity.infrastructure.repositories import UserRepository
from mavic.modules.negotiation.application import rules
from mavic.modules.negotiation.application.example_rules import EXAMPLE_RULES

# Contraseña de los usuarios de ejemplo. Es pública a propósito (está en el
# README): estos usuarios existen solo en bases locales de prueba.
DEMO_PASSWORD = "demo-mavic-2026"  # noqa: S105


def _ask_password() -> str:
    first = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
    second = getpass.getpass("Repetila: ")
    if first != second:
        raise SystemExit("Las contraseñas no coinciden.")
    return first


def create_platform_admin(session: Session, name: str, email: str) -> None:
    user = bootstrap.create_platform_admin(
        session, name=name, email=email, password=_ask_password()
    )
    print(f"Listo: {user.email} es dueño de la plataforma.")


def seed_demo(session: Session) -> None:
    """Crea la empresa de ejemplo FibraSur, sus tres usuarios y sus reglas de negociación.

    Es idempotente y por partes: crea solo lo que falta. Si ya corriste seed-demo
    en un paso anterior, ahora agrega únicamente lo nuevo (las reglas).
    """
    laura = _seed_demo_company(session)
    created_rules = _seed_demo_rules(session, laura)

    print("Datos de ejemplo listos. Contraseña de todos:", DEMO_PASSWORD)
    print("  dueno@mavic-demo.com  dueño de la plataforma")
    print("  laura@fibrasur.com    administradora de FibraSur")
    print("  pablo@fibrasur.com    operador de FibraSur")
    print("  martin@fibrasur.com   supervisor de FibraSur")
    if created_rules:
        print(f"Se crearon {created_rules} reglas de negociación de ejemplo para FibraSur.")


def _seed_demo_company(session: Session) -> Actor:
    """Empresa y usuarios de ejemplo. Devuelve a Laura, la administradora."""
    existing = UserRepository(session).get_by_email("laura@fibrasur.com")
    if existing is not None:
        return Actor(user_id=existing.id, company_id=existing.company_id, role=existing.role)

    owner = bootstrap.create_platform_admin(
        session, name="Dueño de la plataforma", email="dueno@mavic-demo.com", password=DEMO_PASSWORD
    )
    owner_actor = Actor(user_id=owner.id, company_id=None, role=UserRole.PLATFORM_ADMIN)

    fibrasur = companies.create_company_with_admin(
        session,
        actor=owner_actor,
        name="FibraSur",
        admin=companies.NewAdmin(
            name="Laura Gómez", email="laura@fibrasur.com", password=DEMO_PASSWORD
        ),
    )
    laura = Actor(user_id=fibrasur.admin.id, company_id=fibrasur.company.id, role=UserRole.ADMIN)
    for name, email, role in [
        ("Pablo Díaz", "pablo@fibrasur.com", UserRole.OPERATOR),
        ("Martín Ruiz", "martin@fibrasur.com", UserRole.SUPERVISOR),
    ]:
        users.create_user(
            session, actor=laura, name=name, email=email, password=DEMO_PASSWORD, role=role
        )
    return laura


def _seed_demo_rules(session: Session, laura: Actor) -> int:
    """Las reglas de ejemplo, solo si la empresa todavía no tiene ninguna."""
    if rules.list_rules(session, actor=laura):
        return 0
    for data in EXAMPLE_RULES:
        rules.create_rule(session, actor=laura, data=data)
    return len(EXAMPLE_RULES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mavic.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-platform-admin", help="Crear el dueño de la plataforma")
    create.add_argument("--name", required=True)
    create.add_argument("--email", required=True)

    commands.add_parser("seed-demo", help="Crear datos de ejemplo (solo entorno local)")

    args = parser.parse_args(argv)
    settings = get_settings()
    database = Database(settings.database_url.get_secret_value())

    try:
        with database.session() as session:
            if args.command == "create-platform-admin":
                create_platform_admin(session, args.name, args.email)
            elif args.command == "seed-demo":
                if settings.app_env != "local":
                    print("seed-demo solo se puede usar con APP_ENV=local.", file=sys.stderr)
                    return 1
                seed_demo(session)
    except AppError as error:
        print(f"Error: {error.message}", file=sys.stderr)
        return 1
    finally:
        database.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
