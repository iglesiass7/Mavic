"""Configuración de los avisos: verla y cambiarla (pestañas Preventivo y Corriente de Reglas).

Si una empresa nunca la tocó, se muestra la configuración de fábrica (DEFAULTS)
con el envío automático APAGADO: nada sale solo hasta que alguien lo prende.
"""

import uuid
from dataclasses import dataclass
from datetime import time

from sqlalchemy.orm import Session

from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import AuditAction, Subject, changes
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.notices.domain.notices import (
    DEFAULTS,
    Channel,
    NoticeSettings,
    NoticeStage,
    validate,
)
from mavic.modules.notices.domain.senders import SenderFactory
from mavic.modules.notices.infrastructure.orm import NoticeSettingsModel
from mavic.modules.notices.infrastructure.repositories import NoticeSettingsRepository

STAGE_NAME = {
    NoticeStage.PREVENTIVE: "aviso preventivo",
    NoticeStage.DUE_TODAY: "aviso del día de vencimiento",
}
CHANNEL_NAME = {Channel.EMAIL: "Email", Channel.WHATSAPP: "WhatsApp"}


def _from_model(row: NoticeSettingsModel) -> NoticeSettings:
    return NoticeSettings(
        stage=NoticeStage(row.stage),
        enabled=row.enabled,
        channel=Channel(row.channel),
        send_time=row.send_time,
        days_before=row.days_before,
        email_subject=row.email_subject,
        message=row.message,
        instructions=row.instructions,
        whatsapp_template_sid=row.whatsapp_template_sid,
    )


def load_settings(session: Session, company_id: uuid.UUID, stage: NoticeStage) -> NoticeSettings:
    """La configuración guardada, o la de fábrica. No controla permisos (uso interno)."""
    row = NoticeSettingsRepository(session).get(company_id, stage.value)
    return _from_model(row) if row is not None else DEFAULTS[stage]


@dataclass(frozen=True)
class StageSettingsView:
    settings: NoticeSettings
    channel_ready: dict[Channel, bool]  # qué canales tienen sus datos en el .env


def get_settings(
    session: Session, *, actor: Actor, senders: SenderFactory
) -> list[StageSettingsView]:
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()
    ready = {channel: senders.configured(channel) for channel in Channel}
    return [
        StageSettingsView(load_settings(session, company_id, stage), ready) for stage in NoticeStage
    ]


def _readable(s: NoticeSettings) -> dict[str, object]:
    """Para la auditoría: los campos con nombres que entiende cualquiera."""
    data: dict[str, object] = {
        "Envío automático": s.enabled,
        "Canal": CHANNEL_NAME[s.channel],
        "Hora": f"{s.send_time:%H:%M}",
        "Asunto": s.email_subject,
        "Mensaje": s.message,
        "Cómo pagar": s.instructions,
        "Plantilla de WhatsApp": s.whatsapp_template_sid,
    }
    if s.stage is NoticeStage.PREVENTIVE:
        data["Días antes"] = s.days_before
    return data


def update_settings(
    session: Session,
    *,
    actor: Actor,
    senders: SenderFactory,
    stage: NoticeStage,
    enabled: bool,
    channel: Channel,
    send_time: time,
    days_before: int,
    email_subject: str,
    message: str,
    instructions: str,
    whatsapp_template_sid: str | None,
) -> StageSettingsView:
    """Guarda la configuración de un momento. La cambia quien maneja las reglas."""
    actor.require(Permission.MANAGE_RULES)
    company_id = actor.require_company()
    new = validate(
        NoticeSettings(
            stage=stage,
            enabled=enabled,
            channel=channel,
            send_time=send_time.replace(second=0, microsecond=0, tzinfo=None),
            days_before=days_before,
            email_subject=email_subject,
            message=message,
            instructions=instructions,
            whatsapp_template_sid=whatsapp_template_sid,
        )
    )
    repository = NoticeSettingsRepository(session)
    row = repository.get(company_id, stage.value)
    before = _readable(_from_model(row) if row is not None else DEFAULTS[stage])
    if row is None:
        row = NoticeSettingsModel(company_id=company_id, stage=stage.value)
        repository.add(row)
    row.enabled = new.enabled
    row.channel = new.channel.value
    row.send_time = new.send_time
    row.days_before = new.days_before
    row.email_subject = new.email_subject
    row.message = new.message
    row.instructions = new.instructions
    row.whatsapp_template_sid = new.whatsapp_template_sid

    diff = changes(before, _readable(new))
    if diff:
        audit.record(
            session,
            company_id=company_id,
            actor=actor,
            action=AuditAction.REMINDER_SETTINGS_UPDATED,
            subject=Subject("settings", stage.value, f"Configuración del {STAGE_NAME[stage]}"),
            summary=f"Cambió el {STAGE_NAME[stage]}: {', '.join(k.lower() for k in diff)}.",
            details={"cambios": diff},
        )
    session.commit()
    ready = {c: senders.configured(c) for c in Channel}
    return StageSettingsView(new, ready)
