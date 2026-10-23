"""Lecturas y escrituras de los avisos."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import Row, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mavic.modules.notices.infrastructure.orm import NoticeDeliveryModel, NoticeSettingsModel

ACTIVE = ("SENDING", "SENT")


class NoticeSettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def of_company(self, company_id: uuid.UUID) -> dict[str, NoticeSettingsModel]:
        rows = self._session.scalars(
            select(NoticeSettingsModel).where(NoticeSettingsModel.company_id == company_id)
        )
        return {row.stage: row for row in rows}

    def get(self, company_id: uuid.UUID, stage: str) -> NoticeSettingsModel | None:
        return self._session.get(NoticeSettingsModel, (company_id, stage))

    def add(self, settings: NoticeSettingsModel) -> None:
        self._session.add(settings)

    def claim_due_runs(self, *, today: date, now: time) -> list[tuple[uuid.UUID, str]]:
        """Marca como "corrido hoy" cada envío automático al que ya le llegó la hora.

        Es UN solo UPDATE: si dos procesos lo hacen a la vez, cada fila la toma
        uno solo (el otro ya la ve con la fecha de hoy y no la toca).
        """
        s = NoticeSettingsModel
        statement = (
            update(s)
            .where(
                s.enabled.is_(True),
                s.send_time <= now,
                or_(s.last_auto_run_on.is_(None), s.last_auto_run_on < today),
            )
            .values(last_auto_run_on=today)
            .returning(s.company_id, s.stage)
        )
        return [(row.company_id, row.stage) for row in self._session.execute(statement)]


@dataclass(frozen=True)
class LastDelivery:
    invoice_id: uuid.UUID
    stage: str
    channel: str
    status: str
    error: str | None
    created_at: datetime
    sent_at: datetime | None


class DeliveryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim(
        self,
        *,
        company_id: uuid.UUID,
        invoice_id: uuid.UUID,
        stage: str,
        channel: str,
        recipient: str,
        trigger: str,
        requested_by: uuid.UUID | None,
        content: dict[str, Any],
        now: datetime,
    ) -> uuid.UUID | None:
        """Anota "mandando" este aviso. None: ya estaba mandado (o mandándose)."""
        statement = (
            insert(NoticeDeliveryModel)
            .values(
                id=uuid.uuid4(),
                company_id=company_id,
                invoice_id=invoice_id,
                stage=stage,
                channel=channel,
                recipient=recipient[:254],
                status="SENDING",
                trigger=trigger,
                requested_by=requested_by,
                content=content,
                created_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=["invoice_id", "stage"],
                index_where=NoticeDeliveryModel.status.in_(ACTIVE),
            )
            .returning(NoticeDeliveryModel.id)
        )
        return self._session.scalar(statement)

    def finish(
        self,
        delivery_id: uuid.UUID,
        *,
        ok: bool,
        provider_message_id: str | None,
        error: str | None,
        now: datetime,
    ) -> None:
        self._session.execute(
            update(NoticeDeliveryModel)
            .where(NoticeDeliveryModel.id == delivery_id)
            .values(
                status="SENT" if ok else "FAILED",
                provider_message_id=(provider_message_id or None),
                error=(error or None) and error[:1000],
                sent_at=now if ok else None,
            )
        )

    def fail_stale(self, company_id: uuid.UUID, *, older_than: datetime) -> int:
        """Los "mandando" de hace rato quedaron colgados (el proceso se cortó): se liberan."""
        result = self._session.execute(
            update(NoticeDeliveryModel)
            .where(
                NoticeDeliveryModel.company_id == company_id,
                NoticeDeliveryModel.status == "SENDING",
                NoticeDeliveryModel.created_at < older_than,
            )
            .values(status="FAILED", error="El envío se interrumpió antes de terminar.")
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def already_notified(
        self, company_id: uuid.UUID, stage: str, invoice_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not invoice_ids:
            return set()
        d = NoticeDeliveryModel
        return set(
            self._session.scalars(
                select(d.invoice_id).where(
                    d.company_id == company_id,
                    d.stage == stage,
                    d.status.in_(ACTIVE),
                    d.invoice_id.in_(invoice_ids),
                )
            )
        )

    def last_by_invoice(
        self, company_id: uuid.UUID, invoice_ids: list[uuid.UUID]
    ) -> list[LastDelivery]:
        """El último intento de cada aviso (factura y momento), para la lista de facturas."""
        if not invoice_ids:
            return []
        d = NoticeDeliveryModel
        ranked = (
            select(
                d.invoice_id,
                d.stage,
                d.channel,
                d.status,
                d.error,
                d.created_at,
                d.sent_at,
                func.row_number()
                .over(partition_by=(d.invoice_id, d.stage), order_by=d.created_at.desc())
                .label("position"),
            )
            .where(d.company_id == company_id, d.invoice_id.in_(invoice_ids))
            .subquery()
        )
        rows: list[Row[Any]] = list(
            self._session.execute(select(ranked).where(ranked.c.position == 1))
        )
        return [
            LastDelivery(
                invoice_id=r.invoice_id,
                stage=r.stage,
                channel=r.channel,
                status=r.status,
                error=r.error,
                created_at=r.created_at,
                sent_at=r.sent_at,
            )
            for r in rows
        ]

    def sent_counts_by_day(
        self, company_id: uuid.UUID, *, since: datetime, until: datetime, zone: str
    ) -> list[tuple[date, str, int]]:
        """Avisos MANDADOS por día (hora del negocio) y canal: para el medidor de costos."""
        d = NoticeDeliveryModel
        day = func.date(func.timezone(zone, d.sent_at))
        rows = self._session.execute(
            select(day.label("day"), d.channel, func.count().label("n"))
            .where(
                and_(
                    d.company_id == company_id,
                    d.status == "SENT",
                    d.sent_at >= since,
                    d.sent_at < until,
                )
            )
            .group_by(day, d.channel)
        )
        return [(r.day, r.channel, int(r.n)) for r in rows]
