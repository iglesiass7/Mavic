"""La base de datos defiende las reglas de la cartera aunque el código falle.

Estos tests NO pasan por los casos de uso: escriben directo en las tablas,
como lo haría un bug. La idea es comprobar que PostgreSQL rechaza lo que nunca
debería existir, y que dos procesos simultáneos no duplican casos.
"""

import threading
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mavic.core.clock import FixedClock
from mavic.core.db import Database
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.portfolio.application import cases, imports
from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.portfolio.infrastructure.orm import CaseModel, DebtorModel, InvoiceModel
from tests.factories import csv_file, invoice_row, make_company

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("require_db")]

CLOCK = FixedClock(datetime(2026, 10, 16, 15, 0, tzinfo=UTC), "America/Argentina/Buenos_Aires")


def _debtor(database: Database, company_id: uuid.UUID, document: str = "27987654") -> uuid.UUID:
    with database.session() as session:
        debtor = DebtorModel(
            company_id=company_id,
            document_number=document,
            name="Ana Torres",
            phone="+5491155550102",
            email="ana@example.com",
        )
        session.add(debtor)
        session.commit()
        return debtor.id


def _insert_fails(database: Database, row: object) -> bool:
    with database.session() as session:
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            return True
    return False


def test_a_case_cannot_point_to_a_debtor_of_another_company(database: Database) -> None:
    fibra = make_company(database, "FibraSur").company.id
    agua = make_company(database, "AguaNorte").company.id
    ana_de_fibra = _debtor(database, fibra)

    caso_cruzado = CaseModel(company_id=agua, debtor_id=ana_de_fibra, currency="ARS")

    assert _insert_fails(database, caso_cruzado)


def test_an_invoice_cannot_go_to_a_case_of_another_debtor(database: Database) -> None:
    fibra = make_company(database, "FibraSur").company.id
    ana = _debtor(database, fibra, "27987654")
    ricardo = _debtor(database, fibra, "20123456")
    with database.session() as session:
        case = CaseModel(company_id=fibra, debtor_id=ana, currency="ARS")
        session.add(case)
        session.commit()
        case_id = case.id

    factura_de_ricardo_en_caso_de_ana = InvoiceModel(
        company_id=fibra,
        debtor_id=ricardo,
        case_id=case_id,
        external_id="R-1",
        description="Abono",
        amount=Decimal("100"),
        currency="ARS",
        due_date=date(2026, 9, 10),
    )

    assert _insert_fails(database, factura_de_ricardo_en_caso_de_ana)


def test_a_debtor_can_have_only_one_pending_case(database: Database) -> None:
    fibra = make_company(database, "FibraSur").company.id
    ana = _debtor(database, fibra)
    with database.session() as session:
        session.add(CaseModel(company_id=fibra, debtor_id=ana, currency="ARS"))
        # Un caso ya contactado no cuenta: el índice único es PARCIAL.
        session.add(
            CaseModel(company_id=fibra, debtor_id=ana, currency="ARS", status=CaseStatus.CONTACTED)
        )
        # Otra moneda es otro caso (ADR-034).
        session.add(CaseModel(company_id=fibra, debtor_id=ana, currency="USD"))
        session.commit()

    assert _insert_fails(database, CaseModel(company_id=fibra, debtor_id=ana, currency="ARS"))


def test_an_invoice_cannot_go_to_a_case_of_another_currency(database: Database) -> None:
    """Nunca se suman pesos con dólares: la base no deja mezclar monedas en un caso."""
    fibra = make_company(database, "FibraSur").company.id
    ana = _debtor(database, fibra)
    with database.session() as session:
        case = CaseModel(company_id=fibra, debtor_id=ana, currency="ARS")
        session.add(case)
        session.commit()
        case_id = case.id

    factura_en_dolares = InvoiceModel(
        company_id=fibra,
        debtor_id=ana,
        case_id=case_id,
        external_id="U-1",
        description="Equipo importado",
        amount=Decimal("100"),
        currency="USD",
        due_date=date(2026, 9, 10),
    )

    assert _insert_fails(database, factura_en_dolares)


def test_negative_amounts_are_rejected_by_the_database(database: Database) -> None:
    fibra = make_company(database, "FibraSur").company.id
    ana = _debtor(database, fibra)
    invoice = InvoiceModel(
        company_id=fibra,
        debtor_id=ana,
        external_id="F-1",
        description="Abono",
        amount=Decimal("-1"),
        currency="ARS",
        due_date=date(2026, 9, 10),
    )
    assert _insert_fails(database, invoice)


def test_two_simultaneous_generations_do_not_duplicate_cases(database: Database) -> None:
    """Dos operadores apretan "Generar casos" al mismo tiempo.

    Sin el bloqueo por empresa, los dos verían las mismas facturas sin caso y
    los dos intentarían crear casos para los mismos deudores.
    """
    company = make_company(database, "FibraSur")
    actor = Actor(user_id=company.admin.id, company_id=company.company.id, role=UserRole.ADMIN)
    rows = [
        invoice_row(
            external_id=f"F-{i}", debtor_document=f"2000000{i}", debtor_phone=f"+54911555501{i:02d}"
        )
        for i in range(5)
    ]
    with database.session() as session:
        report = imports.import_invoices(
            session, actor=actor, filename="f.csv", content=csv_file(rows), clock=CLOCK
        )
    assert report.is_valid

    start = threading.Barrier(2)
    results: list[cases.GenerationResult] = []
    errors: list[Exception] = []

    def generate() -> None:
        with database.session() as session:
            start.wait()
            try:
                results.append(cases.generate_cases(session, actor=actor, clock=CLOCK))
            except Exception as error:  # noqa: BLE001 - queremos ver cualquier falla
                errors.append(error)

    threads = [threading.Thread(target=generate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert sorted(r.cases_created for r in results) == [0, 5]  # uno hizo todo, el otro nada
    with database.session() as session:
        total = session.scalar(select(func.count()).select_from(CaseModel))
    assert total == 5
