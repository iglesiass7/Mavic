"""Avisos por email y WhatsApp (ADR-038).

- GET  /notice-settings              configuración de los dos momentos (y qué canales andan)
- PUT  /notice-settings/{stage}      cambiarla (permiso de manejar reglas)
- GET  /notices/preview?stage=...    cuántos saldrían ahora y cómo se ve el primero
- POST /notices/send                 mandarlos ya (botón de Facturas; permiso de operar)
- GET  /notices?invoice_id=...       el último aviso de cada factura (columna "Aviso")
"""

from datetime import date, datetime, time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.modules.notices.application import sending
from mavic.modules.notices.application import settings as notice_settings
from mavic.modules.notices.domain.notices import (
    PLACEHOLDERS,
    TEMPLATE_VARIABLES,
    Channel,
    NoticeStage,
)
from mavic.modules.notices.domain.senders import SenderFactory

router = APIRouter(tags=["notices"])


def get_senders(request: Request) -> SenderFactory:
    senders: SenderFactory = request.app.state.notice_senders
    return senders


SendersDep = Annotated[SenderFactory, Depends(get_senders)]


class StageSettingsOut(BaseModel):
    stage: NoticeStage
    enabled: bool
    channel: Channel
    send_time: str  # "09:00", hora argentina
    days_before: int
    email_subject: str
    message: str
    instructions: str
    whatsapp_template_sid: str | None

    @classmethod
    def from_view(cls, view: notice_settings.StageSettingsView) -> "StageSettingsOut":
        s = view.settings
        return cls(
            stage=s.stage,
            enabled=s.enabled,
            channel=s.channel,
            send_time=f"{s.send_time:%H:%M}",
            days_before=s.days_before,
            email_subject=s.email_subject,
            message=s.message,
            instructions=s.instructions,
            whatsapp_template_sid=s.whatsapp_template_sid,
        )


class PlaceholderOut(BaseModel):
    name: str
    description: str


class NoticeSettingsOut(BaseModel):
    stages: list[StageSettingsOut]
    channels_ready: dict[Channel, bool]  # qué canales tienen sus datos en el .env
    placeholders: list[PlaceholderOut]
    template_variables: list[str]  # orden de las variables de una plantilla de WhatsApp


def _settings_out(views: list[notice_settings.StageSettingsView]) -> NoticeSettingsOut:
    return NoticeSettingsOut(
        stages=[StageSettingsOut.from_view(v) for v in views],
        channels_ready=views[0].channel_ready if views else {},
        placeholders=[PlaceholderOut(name=k, description=v) for k, v in PLACEHOLDERS.items()],
        template_variables=TEMPLATE_VARIABLES,
    )


class StageSettingsIn(BaseModel):
    enabled: bool
    channel: Channel
    send_time: time = Field(description="Hora del envío automático (hora argentina), ej. 09:00")
    days_before: int = Field(default=0, ge=0, le=30)
    email_subject: str = Field(default="", max_length=300)
    message: str = Field(max_length=4000)
    instructions: str = Field(default="", max_length=1000)
    whatsapp_template_sid: str | None = Field(default=None, max_length=40)


@router.get("/notice-settings")
def get_notice_settings(
    session: SessionDep, actor: ActorDep, senders: SendersDep
) -> NoticeSettingsOut:
    return _settings_out(notice_settings.get_settings(session, actor=actor, senders=senders))


@router.put("/notice-settings/{stage}")
def update_notice_settings(
    stage: NoticeStage,
    body: StageSettingsIn,
    session: SessionDep,
    actor: ActorDep,
    senders: SendersDep,
) -> NoticeSettingsOut:
    notice_settings.update_settings(
        session, actor=actor, senders=senders, stage=stage, **body.model_dump()
    )
    return _settings_out(notice_settings.get_settings(session, actor=actor, senders=senders))


class PreviewOut(BaseModel):
    stage: NoticeStage
    channel: Channel
    channel_ready: bool
    enabled: bool
    send_time: str
    first_due: date
    last_due: date
    to_send: int
    already_sent: int
    without_contact: int
    sample_subject: str | None
    sample_body: str | None


@router.get("/notices/preview")
def preview_notices(
    stage: NoticeStage, session: SessionDep, actor: ActorDep, clock: ClockDep, senders: SendersDep
) -> PreviewOut:
    view = sending.preview(session, actor=actor, clock=clock, senders=senders, stage=stage)
    return PreviewOut(**view.__dict__)


class SendIn(BaseModel):
    stage: NoticeStage


class SendReportOut(BaseModel):
    stage: NoticeStage
    channel: Channel
    sent: int
    failed: int
    already_sent: int
    without_contact: int
    remaining: int
    errors: list[str]


@router.post("/notices/send")
def send_notices(
    body: SendIn, session: SessionDep, actor: ActorDep, clock: ClockDep, senders: SendersDep
) -> SendReportOut:
    """Manda ya los avisos pendientes. 503 si el canal no está configurado en el .env."""
    report = sending.send_now(session, actor=actor, clock=clock, senders=senders, stage=body.stage)
    return SendReportOut(**report.__dict__)


class InvoiceNoticeOut(BaseModel):
    invoice_id: UUID
    stage: NoticeStage
    channel: Channel
    status: str  # SENDING, SENT, FAILED
    error: str | None
    at: datetime


@router.get("/notices")
def invoice_notices(
    session: SessionDep,
    actor: ActorDep,
    invoice_id: Annotated[list[UUID], Query(max_length=100)],
) -> list[InvoiceNoticeOut]:
    views = sending.notices_for_invoices(session, actor=actor, invoice_ids=invoice_id)
    return [InvoiceNoticeOut(**v.__dict__) for v in views]
