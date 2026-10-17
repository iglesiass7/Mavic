"""Comandos de consola: datos de ejemplo y alta del dueño de la plataforma."""

import pytest
from sqlalchemy import delete, select

from mavic import cli
from mavic.core.config import get_settings
from mavic.core.db import Database
from mavic.modules.identity.infrastructure.orm import UserModel
from mavic.modules.negotiation.infrastructure.orm import NegotiationRuleModel
from tests.conftest import TEST_DATABASE_URL

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def _emails(database: Database) -> list[str]:
    with database.session() as session:
        return sorted(session.scalars(select(UserModel.email)))


def _rule_names(database: Database) -> list[str]:
    with database.session() as session:
        return sorted(session.scalars(select(NegotiationRuleModel.name)))


def test_seed_demo_creates_fibrasur_and_is_idempotent(
    database: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    with database.session() as session:
        cli.seed_demo(session)
    with database.session() as session:
        cli.seed_demo(session)  # la segunda vez no crea nada

    assert _emails(database) == [
        "dueno@mavic-demo.com",
        "laura@fibrasur.com",
        "martin@fibrasur.com",
        "pablo@fibrasur.com",
    ]
    assert len(_rule_names(database)) == 4
    assert capsys.readouterr().out.count("Se crearon 4 reglas") == 1


def test_seed_demo_adds_the_rules_to_a_database_from_a_previous_step(
    database: Database,
) -> None:
    # Una base que ya tenía los usuarios de ejemplo del Paso 2, pero no reglas.
    with database.session() as session:
        cli.seed_demo(session)
        session.execute(delete(NegotiationRuleModel))
        session.commit()

    with database.session() as session:
        cli.seed_demo(session)

    assert "Mora alta con plan extendido" in _rule_names(database)
    assert len(_emails(database)) == 4  # los usuarios no se duplicaron


def test_seed_demo_refuses_to_run_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        assert cli.main(["seed-demo"]) == 1
    finally:
        get_settings.cache_clear()


def test_create_platform_admin_asks_for_the_password_twice(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter(["una frase bien larga", "una frase bien larga"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))

    with database.session() as session:
        cli.create_platform_admin(session, "Mateo", "Mateo@Mavic-Demo.com")

    assert _emails(database) == ["mateo@mavic-demo.com"]


def test_create_platform_admin_rejects_mismatched_passwords(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter(["una frase bien larga", "otra frase distinta"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))

    with database.session() as session, pytest.raises(SystemExit):
        cli.create_platform_admin(session, "Mateo", "mateo@mavic-demo.com")

    assert _emails(database) == []
