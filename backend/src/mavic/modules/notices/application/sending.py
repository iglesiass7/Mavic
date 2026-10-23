"""Mandar los avisos: a mano (botón en Facturas) o solo (todos los días a la hora configurada).

Una tanda, paso a paso:

    1. ¿A quién le toca?  facturas sin caso que vencen en la ventana del momento
    2. Saltear las que ya recibieron este aviso y las que no tienen email/teléfono
    3. Por cada una:  anotar "mandando" (commit) ──> mandar ──> anotar "mandado" o "falló" (commit)
    4. Un evento en la auditoría con el resumen

El paso 3 hace commit ANTES de mandar: si dos tandas corren a la vez, la
segunda choca con el índice único y no manda el mismo aviso otra vez. Si el
proceso se corta en el medio, el "mandando" queda colgado y la próxima tanda
lo da por fallido (y lo vuelve a intentar).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.db import Database
from mavic.core.errors import ExternalServiceError
from mavic.modules.audit.application import audit
from mavic.modules.audit.domain.events import ActorKind, AuditAction
from mavic.modules.identity.application.companies import company_name
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.roles import Permission
from mavic.modules.notices.application.settings import CHANNEL_NAME, STAGE_NAME, load_settings
from mavic.modules.notices.domain.notices import (
    TEMPLATE_VARIABLES,
    Channel,
    InvoiceFacts,
    NoticeSettings,
    NoticeStage,
    recipient_for,
    render,
    values_for,
    window_for,
)
from mavic.modules.notices.domain.senders import DeliveryError, OutgoingMessage, SenderFactory
from mavic.modules.notices.infrastructure.repositories import (
    DeliveryRepository,
    NoticeSettingsRepository,
)
from mavic.modules.portfolio.application.notice_targets import (
    InvoiceContact,
    invoices_due_between,
)

logger = logging.getLogger(__name__)

# Un "mandando" más viejo que esto quedó colgado (el proceso se cortó).
STALE_AFTER = timedelta(minutes=15)
# Tope por tanda manual: que el pedido del botón no tarde demasiado. Lo que quede
# se manda apretando otra vez (o lo manda el envío automático).
MANUAL_LIMIT = 200


def _facts(c: InvoiceContact) -> InvoiceFacts:
    return InvoiceFacts(
        invoice_id=c.invoice_id,
        external_id=c.external_id,
        description=c.description,
        amount=c.amount,
        currency=c.currency,
        due_date=c.due_date,
        debtor_name=c.debtor_name,
        debtor_email=c.debtor_email,
        debtor_phone=c.debtor_phone,
    )


@dataclass(frozen=True)
class Plan:
    settings: NoticeSettings
    first_due: date
    last_due: date
    to_send: list[tuple[InvoiceFacts, str]]  # factura y destinatario
    already_sent: int
    without_contact: int


def _plan(session: Session, *, company_id: uuid.UUID, stage: NoticeStage, today: date) -> Plan:
    settings = load_settings(session, company_id, stage)
    window = window_for(settings, today)
    contacts = invoices_due_between(
        session, company_id=company_id, first=window.first, last=window.last
    )
    facts = [_facts(c) for c in contacts]
    notified = DeliveryRepository(session).already_notified(
        company_id, stage.value, [f.invoice_id for f in facts]
    )
    to_send: list[tuple[InvoiceFacts, str]] = []
    without_contact = 0
    for fact in facts:
        if fact.invoice_id in notified:
            continue
        recipient = recipient_for(settings.channel, fact)
        if recipient is None:
            without_contact += 1
        else:
            to_send.append((fact, recipient))
    return Plan(
        settings=settings,
        first_due=window.first,
        last_due=window.last,
        to_send=to_send,
        already_sent=len(notified),
        without_contact=without_contact,
    )


# ---------------------------------------------------------------- vista previa


@dataclass(frozen=True)
class NoticePreview:
    stage: NoticeStage
    channel: Channel
    channel_ready: bool
    enabled: bool
    send_time: str  # "09:00"
    first_due: date
    last_due: date
    to_send: int
    already_sent: int
    without_contact: int
    sample_subject: str | None  # el primer aviso tal como va a salir
    sample_body: str | None


def preview(
    session: Session, *, actor: Actor, clock: Clock, senders: SenderFactory, stage: NoticeStage
) -> NoticePreview:
    """Cuántos avisos saldrían ahora y cómo se ve el primero (para confirmar antes del botón)."""
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()
    today = clock.today()
    plan = _plan(session, company_id=company_id, stage=stage, today=today)
    subject = body = None
    if plan.to_send:
        message = _message(plan.settings, plan.to_send[0], company_name(session, company_id), today)
        subject, body = message.subject or None, message.body
    return NoticePreview(
        stage=stage,
        channel=plan.settings.channel,
        channel_ready=senders.configured(plan.settings.channel),
        enabled=plan.settings.enabled,
        send_time=f"{plan.settings.send_time:%H:%M}",
        first_due=plan.first_due,
        last_due=plan.last_due,
        to_send=len(plan.to_send),
        already_sent=plan.already_sent,
        without_contact=plan.without_contact,
        sample_subject=subject,
        sample_body=body,
    )


def _message(
    settings: NoticeSettings, target: tuple[InvoiceFacts, str], company: str, today: date
) -> OutgoingMessage:
    fact, recipient = target
    values = values_for(fact, company=company, today=today, instructions=settings.instructions)
    body = render(settings.message, values)
    # Si "Cómo pagar" quedó vacío, no dejar renglones en blanco de más.
    while "\n\n\n" in body:
        body = body.replace("\n\n\n", "\n\n")
    if settings.channel is Channel.EMAIL:
        return OutgoingMessage(
            to=recipient, subject=render(settings.email_subject, values), body=body.strip()
        )
    variables = {str(i): values[name] for i, name in enumerate(TEMPLATE_VARIABLES, start=1)}
    return OutgoingMessage(
        to=recipient,
        body=body.strip(),
        template_sid=settings.whatsapp_template_sid,
        template_variables=variables if settings.whatsapp_template_sid else {},
    )


# ---------------------------------------------------------------- mandar


@dataclass(frozen=True)
class SendReport:
    stage: NoticeStage
    channel: Channel
    sent: int
    failed: int
    already_sent: int
    without_contact: int
    remaining: int  # quedaron para otra tanda (tope del botón)
    errors: list[str] = field(default_factory=list)  # los primeros motivos de falla


def _unavailable(channel: Channel) -> ExternalServiceError:
    if channel is Channel.EMAIL:
        missing = "SMTP_HOST y SMTP_FROM"
    else:
        missing = "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM"
    return ExternalServiceError(
        f"El canal {CHANNEL_NAME[channel]} no está configurado: faltan {missing} en el .env.",
        service=channel.value,
        retriable=False,
        code="NOTICE_CHANNEL_NOT_CONFIGURED",
    )


def _send(
    session: Session,
    *,
    clock: Clock,
    senders: SenderFactory,
    company_id: uuid.UUID,
    stage: NoticeStage,
    actor: Actor | None,
    limit: int | None,
) -> SendReport:
    today = clock.today()
    deliveries = DeliveryRepository(session)
    deliveries.fail_stale(company_id, older_than=clock.now() - STALE_AFTER)
    session.commit()

    plan = _plan(session, company_id=company_id, stage=stage, today=today)
    channel = plan.settings.channel
    sender = senders.sender_for(channel) if plan.to_send else None
    if plan.to_send and sender is None:
        raise _unavailable(channel)

    batch = plan.to_send if limit is None else plan.to_send[:limit]
    company = company_name(session, company_id)
    sent = failed = 0
    errors: list[str] = []
    try:
        for target in batch:
            message = _message(plan.settings, target, company, today)
            delivery_id = deliveries.claim(
                company_id=company_id,
                invoice_id=target[0].invoice_id,
                stage=stage.value,
                channel=channel.value,
                recipient=message.to,
                trigger="MANUAL" if actor else "AUTOMATIC",
                requested_by=actor.user_id if actor else None,
                content={"subject": message.subject, "body": message.body},
                now=clock.now(),
            )
            session.commit()
            if delivery_id is None:
                continue  # otra tanda lo está mandando o ya lo mandó
            assert sender is not None  # noqa: S101 - hay a quién mandar, así que hay remitente
            try:
                provider_id = sender.send(message)
            except DeliveryError as exc:
                failed += 1
                if len(errors) < 5:
                    errors.append(f"{target[0].external_id}: {exc}")
                deliveries.finish(
                    delivery_id, ok=False, provider_message_id=None, error=str(exc), now=clock.now()
                )
            else:
                sent += 1
                deliveries.finish(
                    delivery_id,
                    ok=True,
                    provider_message_id=provider_id,
                    error=None,
                    now=clock.now(),
                )
            session.commit()
    finally:
        if sender is not None:
            sender.close()

    report = SendReport(
        stage=stage,
        channel=channel,
        sent=sent,
        failed=failed,
        already_sent=plan.already_sent,
        without_contact=plan.without_contact,
        remaining=len(plan.to_send) - len(batch),
        errors=errors,
    )
    if actor is not None or sent or failed:
        _audit(session, company_id=company_id, actor=actor, report=report, plan=plan)
        session.commit()
    return report


def _audit(
    session: Session, *, company_id: uuid.UUID, actor: Actor | None, report: SendReport, plan: Plan
) -> None:
    how = "a mano" if actor else "automático"
    parts = [f"{report.sent} mandados por {CHANNEL_NAME[report.channel]}"]
    if report.failed:
        parts.append(f"{report.failed} fallaron")
    if report.without_contact:
        parts.append(f"{report.without_contact} sin datos de contacto")
    audit.record(
        session,
        company_id=company_id,
        actor=actor,
        actor_kind=None if actor else ActorKind.SYSTEM,
        action=AuditAction.REMINDERS_SENT,
        summary=f"Envío {how} del {STAGE_NAME[report.stage]}: {', '.join(parts)}.",
        details={
            "facturas_que_vencen": f"{plan.first_due:%d/%m/%Y} a {plan.last_due:%d/%m/%Y}",
            "mandados": report.sent,
            "fallaron": report.failed,
            "ya_avisadas": report.already_sent,
            "sin_contacto": report.without_contact,
            "errores": report.errors,
        },
    )


def send_now(
    session: Session, *, actor: Actor, clock: Clock, senders: SenderFactory, stage: NoticeStage
) -> SendReport:
    """El botón de Facturas: manda ya los avisos pendientes de ese momento."""
    actor.require(Permission.OPERATE_PORTFOLIO)
    company_id = actor.require_company()
    return _send(
        session,
        clock=clock,
        senders=senders,
        company_id=company_id,
        stage=stage,
        actor=actor,
        limit=MANUAL_LIMIT,
    )


# ---------------------------------------------------------------- envío automático


def run_scheduled(database: Database, *, clock: Clock, senders: SenderFactory) -> list[SendReport]:
    """Lo que hace el proceso de fondo (worker) cada minuto.

    Toma los envíos a los que ya les llegó la hora y todavía no corrieron hoy, y
    los manda. Cada empresa y momento en su propia transacción: si una falla,
    las demás siguen.
    """
    now_local = clock.now().astimezone(clock.zone())
    with database.session() as session:
        due = NoticeSettingsRepository(session).claim_due_runs(
            today=now_local.date(), now=now_local.time().replace(tzinfo=None)
        )
        session.commit()

    reports: list[SendReport] = []
    for company_id, stage_value in due:
        stage = NoticeStage(stage_value)
        with database.session() as session:
            try:
                reports.append(
                    _send(
                        session,
                        clock=clock,
                        senders=senders,
                        company_id=company_id,
                        stage=stage,
                        actor=None,
                        limit=None,
                    )
                )
            except ExternalServiceError as exc:
                session.rollback()
                logger.warning("Avisos de %s (%s) sin mandar: %s", company_id, stage, exc.message)
                audit.record(
                    session,
                    company_id=company_id,
                    actor_kind=ActorKind.SYSTEM,
                    action=AuditAction.REMINDERS_NOT_SENT,
                    summary=f"No se mandó el {STAGE_NAME[stage]} automático: {exc.message}",
                )
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Falló el envío automático de %s (%s)", company_id, stage)
    return reports


# ---------------------------------------------------------------- consultas


@dataclass(frozen=True)
class InvoiceNotice:
    invoice_id: uuid.UUID
    stage: NoticeStage
    channel: Channel
    status: str  # SENDING, SENT, FAILED
    error: str | None
    at: datetime  # cuándo se mandó (o cuándo se intentó)


def notices_for_invoices(
    session: Session, *, actor: Actor, invoice_ids: list[uuid.UUID]
) -> list[InvoiceNotice]:
    """El último aviso de cada factura (para la columna "Aviso" de Facturas)."""
    actor.require(Permission.VIEW_PORTFOLIO)
    company_id = actor.require_company()
    return [
        InvoiceNotice(
            invoice_id=d.invoice_id,
            stage=NoticeStage(d.stage),
            channel=Channel(d.channel),
            status=d.status,
            error=d.error,
            at=d.sent_at or d.created_at,
        )
        for d in DeliveryRepository(session).last_by_invoice(company_id, invoice_ids)
    ]


@dataclass(frozen=True)
class DailyNoticeUsage:
    day: date
    channel: Channel
    sent: int


def sent_by_day(
    session: Session, *, company_id: uuid.UUID, since: datetime, until: datetime, zone: str
) -> list[DailyNoticeUsage]:
    """Avisos mandados por día y canal (lo usa el medidor de costos, que ya controló permisos)."""
    return [
        DailyNoticeUsage(day, Channel(channel), count)
        for day, channel, count in DeliveryRepository(session).sent_counts_by_day(
            company_id, since=since, until=until, zone=zone
        )
    ]
