"""Acceso a conversaciones y acuerdos."""

import uuid

from sqlalchemy import select
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
