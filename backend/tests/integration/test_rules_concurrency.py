"""Concurrencia: dos administradoras crean AL MISMO TIEMPO reglas que se pisan.

Sin bloqueo, cada una revisa las reglas existentes, no ve la de la otra (todavía
no se guardó) y se guardan las dos: habría casos con dos ofertas posibles.

Con el bloqueo por empresa, la segunda espera a que la primera termine, ve la
regla nueva y se rechaza con RULE_OVERLAP.

Para que el test no dependa de la suerte, se fuerza el PEOR orden posible: después
de revisar las reglas, cada hilo espera (hasta 1 segundo) a que el otro también
haya revisado. Sin bloqueo, los dos revisan, no ven nada y guardan: el test falla.
Con bloqueo, el segundo ni siquiera puede revisar hasta que el primero termina.
"""

import contextlib
import threading
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from mavic.core.db import Database
from mavic.core.errors import ConflictError
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.negotiation.application import rules
from mavic.modules.negotiation.domain.rules import Interval, PaymentTerms, RuleConditions
from mavic.modules.negotiation.infrastructure.orm import NegotiationRuleModel
from tests.factories import make_company, make_user

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]


def _rule(name: str, age: Interval[int]) -> rules.RuleData:
    return rules.RuleData(
        name=name,
        description="",
        conditions=RuleConditions(Interval(Decimal("0"), None), age, Interval(1, None)),
        terms=PaymentTerms(
            discount_pct=Decimal("10"),
            payment_days=5,
            max_installments=3,
            interest_pct=Decimal("0"),
        ),
    )


def test_two_admins_cannot_create_overlapping_rules_at_the_same_time(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    both_checked = threading.Barrier(2, timeout=1)
    original_check = rules._check_against_others

    def check_and_wait_for_the_other(*args: Any, **kwargs: Any) -> None:
        original_check(*args, **kwargs)
        # Con bloqueo, el otro hilo nunca llega acá a tiempo: se sigue sin él.
        with contextlib.suppress(threading.BrokenBarrierError):
            both_checked.wait()

    monkeypatch.setattr(rules, "_check_against_others", check_and_wait_for_the_other)
    company = make_company(database, admin_email="laura@fibrasur.com")
    sofia = make_user(database, company, "sofia@fibrasur.com", UserRole.ADMIN)
    company_id = company.company.id

    start = threading.Barrier(2)
    results: list[str] = []

    def create(user_id: uuid.UUID, data: rules.RuleData) -> None:
        actor = Actor(user_id=user_id, company_id=company_id, role=UserRole.ADMIN)
        with database.session() as session:
            start.wait()
            try:
                rules.create_rule(session, actor=actor, data=data)
                results.append("ok")
            except ConflictError as error:
                results.append(error.code)

    threads = [
        threading.Thread(target=create, args=(company.admin.id, _rule("A", Interval(15, 59)))),
        threading.Thread(target=create, args=(sofia.id, _rule("B", Interval(30, 90)))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results) == ["RULE_OVERLAP", "ok"]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(NegotiationRuleModel)) == 1
