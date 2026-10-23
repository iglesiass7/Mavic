"""Acceso a conversaciones y acuerdos."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mavic.modules.voice.infrastructure.orm import (
    AgreementInstallmentModel,
    ConversationModel,
    PaymentAgreementModel,
    WebhookEventModel,
)

# Una llamada "en curso": todavía puede terminar y traer un resultado.
ACTIVE_STATUSES = ("INITIATING", "INITIATED", "IN_PROGRESS")


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
                origin="TOOLS",
                status="IN_PROGRESS",
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

    def add(self, conversation: ConversationModel) -> None:
        self._session.add(conversation)

    def get_for_update(self, conversation_id: uuid.UUID) -> ConversationModel | None:
        return self._session.scalar(
            select(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def has_active_call(
        self, company_id: uuid.UUID, case_id: uuid.UUID, *, since: datetime
    ) -> bool:
        """¿Hay una llamada de ese caso empezada después de `since` y sin terminar?"""
        c = ConversationModel
        found = self._session.scalar(
            select(func.count()).where(
                c.company_id == company_id,
                c.case_id == case_id,
                c.status.in_(ACTIVE_STATUSES),
                c.created_at >= since,
            )
        )
        return bool(found)

    def awaiting_webhook(
        self, company_id: uuid.UUID, case_id: uuid.UUID
    ) -> ConversationModel | None:
        """La llamada saliente más reciente del caso que todavía espera su webhook.

        Sirve si el webhook llega ANTES de que Mavic guarde el conversation_id
        que devolvió ElevenLabs: se la encuentra por el caso.
        """
        c = ConversationModel
        return self._session.scalar(
            select(c)
            .where(
                c.company_id == company_id,
                c.case_id == case_id,
                c.origin == "OUTBOUND",
                c.status.in_(("INITIATING", "INITIATED")),
                c.provider_conversation_id.is_(None),
            )
            .order_by(c.created_at.desc())
            .limit(1)
            .with_for_update()
        )

    def page_of_company(
        self,
        company_id: uuid.UUID,
        *,
        statuses: tuple[str, ...] | None,
        result: str | None,
        since: datetime | None,
        until: datetime | None,
        case_ids: set[uuid.UUID] | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ConversationModel], int]:
        """Las llamadas de la empresa, de la más nueva a la más vieja."""
        c = ConversationModel
        query = select(c).where(c.company_id == company_id)
        if statuses is not None:
            query = query.where(c.status.in_(statuses))
        if result is not None:
            query = query.where(c.result == result)
        if since is not None:
            query = query.where(c.created_at >= since)
        if until is not None:
            query = query.where(c.created_at < until)
        if case_ids is not None:
            query = query.where(c.case_id.in_(case_ids))
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.scalars(
            query.order_by(c.created_at.desc(), c.id).limit(limit).offset(offset)
        )
        return list(rows), total

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


# Llamadas que NO cuentan en el tablero: las que no se pudieron iniciar y las
# que todavía esperan su webhook (no se sabe cómo terminaron).
_NOT_FINISHED = ("FAILED", "INITIATING", "INITIATED")


def call_totals(session: Session, company_id: uuid.UUID) -> CallTotals:
    c = ConversationModel
    counted = (c.company_id == company_id) & c.status.not_in(_NOT_FINISHED)
    row = session.execute(
        select(
            func.count(), func.count().filter(c.identity_verified), func.max(c.created_at)
        ).where(counted)
    ).one()
    results = session.execute(
        select(c.result, func.count()).where(counted, c.result.is_not(None)).group_by(c.result)
    ).all()
    return CallTotals(
        calls=int(row[0]),
        identity_verified=int(row[1]),
        by_result={str(result): int(count) for result, count in results},
        last_call_at=row[2],
    )


def call_seconds_by_day(
    session: Session, company_id: uuid.UUID, *, since: datetime, until: datetime, zone: str
) -> list[tuple[date, int, int]]:
    """Por día (hora del negocio): llamadas con duración y segundos hablados.

    Cuenta las que informaron duración (llegó su webhook), sin importar el resultado:
    el proveedor cobra el minuto aunque la llamada no termine en acuerdo.
    """
    c = ConversationModel
    day = func.date(func.timezone(zone, c.created_at))
    rows = session.execute(
        select(day.label("day"), func.count(), func.sum(c.call_duration_secs))
        .where(
            c.company_id == company_id,
            c.call_duration_secs.is_not(None),
            c.created_at >= since,
            c.created_at < until,
        )
        .group_by(day)
    )
    return [(r[0], int(r[1]), int(r[2] or 0)) for r in rows]


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

    def of_case(self, company_id: uuid.UUID, case_id: uuid.UUID) -> list[PaymentAgreementModel]:
        a = PaymentAgreementModel
        query = (
            select(a)
            .where(a.company_id == company_id, a.case_id == case_id)
            .order_by(a.created_at.desc())
        )
        return list(self._session.scalars(query))

    def get_for_update(
        self, company_id: uuid.UUID, agreement_id: uuid.UUID
    ) -> PaymentAgreementModel | None:
        """El acuerdo, bloqueado: dos personas registrando pagos a la vez no se pisan."""
        a = PaymentAgreementModel
        return self._session.scalar(
            select(a)
            .where(a.company_id == company_id, a.id == agreement_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    # ------------------------------------------------------------ cuotas

    def add_installment(self, installment: AgreementInstallmentModel) -> None:
        self._session.add(installment)

    def installment_for_update(
        self, agreement_id: uuid.UUID, number: int
    ) -> AgreementInstallmentModel | None:
        i = AgreementInstallmentModel
        return self._session.scalar(
            select(i)
            .where(i.agreement_id == agreement_id, i.number == number)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def installments_of(
        self, agreement_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[AgreementInstallmentModel]]:
        if not agreement_ids:
            return {}
        i = AgreementInstallmentModel
        query = (
            select(i).where(i.agreement_id.in_(agreement_ids)).order_by(i.agreement_id, i.number)
        )
        result: dict[uuid.UUID, list[AgreementInstallmentModel]] = {}
        for installment in self._session.scalars(query):
            result.setdefault(installment.agreement_id, []).append(installment)
        return result

    def all_installments(
        self, company_id: uuid.UUID
    ) -> dict[uuid.UUID, list[AgreementInstallmentModel]]:
        """Todas las cuotas de la empresa, por acuerdo (para el tablero)."""
        i = AgreementInstallmentModel
        query = select(i).where(i.company_id == company_id).order_by(i.agreement_id, i.number)
        result: dict[uuid.UUID, list[AgreementInstallmentModel]] = {}
        for installment in self._session.scalars(query):
            result.setdefault(installment.agreement_id, []).append(installment)
        return result


class WebhookEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def store(self, event: WebhookEventModel) -> WebhookEventModel:
        """Guarda el envío; si ya estaba (mismo cuerpo), devuelve el guardado.

        `ON CONFLICT DO NOTHING` + lectura con bloqueo: si ElevenLabs manda el
        mismo aviso dos veces a la vez, se procesa una sola.
        """
        self._session.execute(
            insert(WebhookEventModel)
            .values(
                id=event.id,
                body_sha256=event.body_sha256,
                event_type=event.event_type,
                provider_conversation_id=event.provider_conversation_id,
                payload=event.payload,
                received_at=event.received_at,
            )
            .on_conflict_do_nothing(index_elements=["body_sha256"])
        )
        stored = self._session.scalar(
            select(WebhookEventModel)
            .where(WebhookEventModel.body_sha256 == event.body_sha256)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert stored is not None  # noqa: S101 - se acaba de insertar o ya existía
        return stored
