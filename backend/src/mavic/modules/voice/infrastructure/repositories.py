"""Acceso a conversaciones y acuerdos."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mavic.modules.voice.infrastructure.orm import ConversationModel, PaymentAgreementModel


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def open_for_update(
        self, provider_conversation_id: str, company_id: uuid.UUID, case_id: uuid.UUID
    ) -> ConversationModel:
        """La conversación de esa llamada, creándola si es la primera herramienta que se usa.

        La deja BLOQUEADA hasta el final de la transacción.

        Por qué no "buscar y, si no está, crear": el agente puede llamar a dos
        herramientas casi a la vez. Las dos buscarían, no encontrarían nada e
        intentarían crear la misma fila. `INSERT ... ON CONFLICT DO NOTHING` hace
        las dos cosas en un solo paso atómico: si otra transacción ya la creó, no
        hace nada. Después, `SELECT ... FOR UPDATE` la bloquea: la segunda
        herramienta espera a que termine la primera y ve sus cambios.
        """
        self._session.execute(
            insert(ConversationModel)
            .values(
                id=uuid.uuid4(),
                company_id=company_id,
                case_id=case_id,
                provider_conversation_id=provider_conversation_id,
                identity_verified=False,
                single_payment_offered=False,
                installments_offered=False,
            )
            .on_conflict_do_nothing(index_elements=["provider_conversation_id"])
        )
        conversation = self._session.scalar(
            select(ConversationModel)
            .where(ConversationModel.provider_conversation_id == provider_conversation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert conversation is not None  # noqa: S101 - se acaba de insertar o ya existía
        return conversation

    def by_provider_id(self, provider_conversation_id: str) -> ConversationModel | None:
        return self._session.scalar(
            select(ConversationModel)
            .where(ConversationModel.provider_conversation_id == provider_conversation_id)
            .with_for_update()
        )

    def of_case(self, company_id: uuid.UUID, case_id: uuid.UUID) -> list[ConversationModel]:
        return list(
            self._session.scalars(
                select(ConversationModel)
                .where(
                    ConversationModel.company_id == company_id,
                    ConversationModel.case_id == case_id,
                )
                .order_by(ConversationModel.created_at)
            )
        )


@dataclass(frozen=True)
class CallTotals:
    calls: int
    identity_verified: int
    by_result: dict[str, int]  # solo los resultados que aparecen
    last_call_at: datetime | None


@dataclass(frozen=True)
class AgreementTotals:
    agreements: int
    single_payment: int
    installments: int
    original_amount: Decimal  # lo que se debía en los casos con acuerdo
    agreed_amount: Decimal  # lo que el deudor se comprometió a pagar


def call_totals(session: Session, company_id: uuid.UUID) -> CallTotals:
    c = ConversationModel
    row = session.execute(
        select(
            func.count(), func.count().filter(c.identity_verified), func.max(c.created_at)
        ).where(c.company_id == company_id)
    ).one()
    results = session.execute(
        select(c.result, func.count())
        .where(c.company_id == company_id, c.result.is_not(None))
        .group_by(c.result)
    ).all()
    return CallTotals(
        calls=int(row[0]),
        identity_verified=int(row[1]),
        by_result={str(result): int(count) for result, count in results},
        last_call_at=row[2],
    )


def agreement_totals(session: Session, company_id: uuid.UUID) -> AgreementTotals:
    a = PaymentAgreementModel
    single = a.installment_count == 1
    row = session.execute(
        select(
            func.count(),
            func.count().filter(single),
            func.count().filter(~single),
            func.coalesce(func.sum(a.original_amount), 0),
            func.coalesce(func.sum(a.total_amount), 0),
        ).where(a.company_id == company_id)
    ).one()
    return AgreementTotals(
        agreements=int(row[0]),
        single_payment=int(row[1]),
        installments=int(row[2]),
        original_amount=Decimal(row[3]),
        agreed_amount=Decimal(row[4]),
    )


class AgreementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, agreement: PaymentAgreementModel) -> None:
        self._session.add(agreement)

    def by_conversations(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, PaymentAgreementModel]:
        if not conversation_ids:
            return {}
        query = select(PaymentAgreementModel).where(
            PaymentAgreementModel.conversation_id.in_(conversation_ids)
        )
        return {a.conversation_id: a for a in self._session.scalars(query)}
