"""Uso del agente para el medidor de costos: minutos de llamada por día."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from mavic.modules.voice.infrastructure.repositories import call_seconds_by_day


@dataclass(frozen=True)
class DailyCallUsage:
    day: date
    calls: int
    seconds: int


def calls_by_day(
    session: Session, *, company_id: uuid.UUID, since: datetime, until: datetime, zone: str
) -> list[DailyCallUsage]:
    """No controla permisos: lo llama el medidor de costos, que ya los controló."""
    return [
        DailyCallUsage(day, calls, seconds)
        for day, calls, seconds in call_seconds_by_day(
            session, company_id, since=since, until=until, zone=zone
        )
    ]
