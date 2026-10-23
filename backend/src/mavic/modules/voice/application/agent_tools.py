"""Las cuatro herramientas que el agente de ElevenLabs llama DURANTE la llamada.

    1. obtener_contexto_del_caso   ¿hablo con el titular? -> datos de la deuda
    2. obtener_oferta_pago_unico   -> pago único con descuento
    3. obtener_oferta_cuotas       -> plan en cuotas
    4. registrar_resultado         -> acuerdo, desconocimiento, contactado o derivación

QUIÉN PUEDE LLAMARLAS: el agente, con un token secreto (ver api/agent_routes.py).
No hay un usuario con sesión, así que no se usan los permisos por rol: el
alcance de cada llamada es UN caso (el `caso_id` que el agente recibió al
empezar) y todo se busca dentro de la empresa de ese caso.

CADA LLAMADA ES UNA FILA EN `conversations`, identificada por el
`conversation_id` de ElevenLabs. Ahí se guarda qué pasó (identidad verificada,
ofertas dichas, resultado) para que cada herramienta sepa lo que hicieron las
anteriores, y para que el operador lo vea después.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import ConflictError, NotFoundError
from mavic.modules.identity.application.companies import company_name
from mavic.modules.negotiation.application.offers import compute_case_offers
from mavic.modules.negotiation.domain.offers import InstallmentsOffer, SinglePaymentOffer
from mavic.modules.portfolio.application import cases as portfolio
from mavic.modules.voice.application.payments import add_installments
from mavic.modules.voice.domain.call_offers import CallOffers, OfferProgress
from mavic.modules.voice.domain.call_payload import case_number_from_reference
from mavic.modules.voice.domain.identity import identity_verified
from mavic.modules.voice.domain.outcomes import (
    CASE_STATUS_FOR_RESULT,
    CallResult,
    Rejection,
    check_registration,
)
from mavic.modules.voice.domain.payments import DEFAULT_PAYMENT_DAYS
from mavic.modules.voice.infrastructure import offer_codec
from mavic.modules.voice.infrastructure.orm import ConversationModel, PaymentAgreementModel
from mavic.modules.voice.infrastructure.repositories import (
    AgreementRepository,
    ConversationRepository,
)

NO_OFFER_ID = "SIN-OFERTA"


class NoOfferReason:
    """Por qué una herramienta de ofertas no ofrece nada (`motivo` para el agente)."""

    IDENTIDAD_NO_VERIFICADA = "IDENTIDAD_NO_VERIFICADA"
    SIN_REGLA = "SIN_REGLA"  # ninguna regla de la empresa se aplica a este caso
    CASO_NO_NEGOCIABLE = "CASO_NO_NEGOCIABLE"  # el caso ya tiene un resultado
    SIN_CUOTAS = "SIN_CUOTAS"  # la regla permite solo pago único


_REASON_FROM_NEGOTIATION = {
    "NO_MATCHING_RULE": NoOfferReason.SIN_REGLA,
    "CASE_NOT_NEGOTIABLE": NoOfferReason.CASO_NO_NEGOCIABLE,
}


# ---------------------------------------------------------------- resultados


@dataclass(frozen=True)
class DebtDetails:
    creditor_name: str
    debt_context: str
    original_amount: Decimal
    currency: str
    original_due_date: date


@dataclass(frozen=True)
class CaseContext:
    case_reference: str
    debtor_name: str
    identity_verified: bool
    progress: OfferProgress
    debt: DebtDetails | None  # None si no se verificó la identidad


@dataclass(frozen=True)
class SinglePaymentAnswer:
    progress: OfferProgress
    offer: SinglePaymentOffer | None
    reason: str | None
    # Lo que se informa cuando no hay oferta: el monto completo, sin descuento
    # (pedido de quien arma el agente). Si no se verificó la identidad, 0.
    fallback_amount: Decimal


@dataclass(frozen=True)
class InstallmentsAnswer:
    progress: OfferProgress
    offer: InstallmentsOffer | None
    reason: str | None
    fallback_amount: Decimal


@dataclass(frozen=True)
class RegistrationAnswer:
    registered: bool
    result: CallResult
    offer_id: str | None
    rejection: Rejection | None


# ---------------------------------------------------------------- piezas comunes


@dataclass
class _Call:
    company_id: uuid.UUID
    case_id: uuid.UUID
    conversation: ConversationModel


def _open_call(session: Session, case_reference: str, provider_conversation_id: str) -> _Call:
    number = case_number_from_reference(case_reference)
    ref = portfolio.find_case_by_number(session, number) if number is not None else None
    if ref is None:
        raise NotFoundError(f"No existe el caso '{case_reference}'.", code="CASE_NOT_FOUND")
    conversation = ConversationRepository(session).open_for_update(
        provider_conversation_id, ref.company_id, ref.id
    )
    if conversation.case_id != ref.id:
        # El mismo id de conversación no puede saltar de un caso a otro.
        raise ConflictError(
            "Esta conversación pertenece a otro caso.", code="CONVERSATION_OF_OTHER_CASE"
        )
    return _Call(ref.company_id, ref.id, conversation)


def _call_offers(session: Session, call: _Call, clock: Clock) -> CallOffers:
    """Las ofertas de la llamada: se calculan la primera vez y después se reusan."""
    conversation = call.conversation
    if conversation.offers is not None:
        return offer_codec.decode(conversation.offers)

    view = compute_case_offers(
        session, company_id=call.company_id, clock=clock, case_id=call.case_id
    )
    offers = CallOffers(
        total_amount=view.facts.total_amount,
        currency=view.currency,
        rule_name=view.rule.name if view.rule else None,
        no_offer_reason=_REASON_FROM_NEGOTIATION[view.reason.value] if view.reason else None,
        single_payment=view.offers.single_payment if view.offers else None,
        installments=view.offers.installments if view.offers else None,
    )
    conversation.offers = offer_codec.encode(offers)
    return offers


def _progress(conversation: ConversationModel, offers: CallOffers) -> OfferProgress:
    return OfferProgress(
        offers=offers,
        single_offered=conversation.single_payment_offered,
        installments_offered=conversation.installments_offered,
    )


# ---------------------------------------------------------------- 1. contexto


def get_case_context(
    session: Session,
    *,
    clock: Clock,
    case_reference: str,
    provider_conversation_id: str,
    asked_name: str,
    answer: str | bool,
) -> CaseContext:
    call = _open_call(session, case_reference, provider_conversation_id)
    detail = portfolio.case_detail(
        session, company_id=call.company_id, clock=clock, case_id=call.case_id
    )
    summary = detail.summary
    verified = identity_verified(asked_name, answer, summary.debtor.name)
    call.conversation.identity_verified = verified
    offers = _call_offers(session, call, clock)

    debt = None
    if verified:
        descriptions = list(dict.fromkeys(invoice.description for invoice in detail.invoices))
        debt = DebtDetails(
            creditor_name=company_name(session, call.company_id),
            debt_context=", ".join(descriptions),
            original_amount=summary.total_amount,
            currency=detail.invoices[0].currency,
            original_due_date=summary.oldest_due_date,
        )
    session.commit()
    return CaseContext(
        case_reference=case_reference,
        debtor_name=summary.debtor.name,
        identity_verified=verified,
        progress=_progress(call.conversation, offers),
        debt=debt,
    )


# ---------------------------------------------------------------- 2 y 3. ofertas


def get_single_payment_offer(
    session: Session, *, clock: Clock, case_reference: str, provider_conversation_id: str
) -> SinglePaymentAnswer:
    call = _open_call(session, case_reference, provider_conversation_id)
    offers = _call_offers(session, call, clock)
    conversation = call.conversation

    if not conversation.identity_verified:
        answer = SinglePaymentAnswer(
            _progress(conversation, offers), None, NoOfferReason.IDENTIDAD_NO_VERIFICADA, Decimal(0)
        )
    elif offers.single_payment is None:
        reason = offers.no_offer_reason or NoOfferReason.SIN_REGLA
        answer = SinglePaymentAnswer(
            _progress(conversation, offers), None, reason, offers.total_amount
        )
    else:
        conversation.single_payment_offered = True
        answer = SinglePaymentAnswer(
            _progress(conversation, offers), offers.single_payment, None, offers.total_amount
        )
    session.commit()
    return answer


def get_installments_offer(
    session: Session, *, clock: Clock, case_reference: str, provider_conversation_id: str
) -> InstallmentsAnswer:
    call = _open_call(session, case_reference, provider_conversation_id)
    offers = _call_offers(session, call, clock)
    conversation = call.conversation

    if not conversation.identity_verified:
        answer = InstallmentsAnswer(
            _progress(conversation, offers), None, NoOfferReason.IDENTIDAD_NO_VERIFICADA, Decimal(0)
        )
    elif offers.installments is None:
        reason = offers.no_offer_reason or NoOfferReason.SIN_CUOTAS
        answer = InstallmentsAnswer(
            _progress(conversation, offers), None, reason, offers.total_amount
        )
    else:
        conversation.installments_offered = True
        answer = InstallmentsAnswer(
            _progress(conversation, offers), offers.installments, None, offers.total_amount
        )
    session.commit()
    return answer


# ---------------------------------------------------------------- 4. resultado


def register_result(
    session: Session,
    *,
    clock: Clock,
    case_reference: str,
    provider_conversation_id: str,
    result: CallResult,
    offer_id: str | None,
    final_confirmation: bool,
    unknown_count: int,
) -> RegistrationAnswer:
    """Registra el resultado de la llamada: estado del caso y, si hubo acuerdo, el acuerdo.

    Todo en UNA transacción: o se guarda todo (resultado + estado + acuerdo) o nada.
    Si el agente reintenta con lo mismo, responde "registrado" sin duplicar.
    """
    offer_id = offer_id.strip() if offer_id and offer_id.strip() else None
    call = _open_call(session, case_reference, provider_conversation_id)
    conversation = call.conversation

    def answer(rejection: Rejection | None = None) -> RegistrationAnswer:
        return RegistrationAnswer(rejection is None, result, offer_id, rejection)

    # ¿Ya se registró esta llamada? Mismo pedido: OK sin repetir. Otro: rechazo.
    if conversation.result is not None:
        same = conversation.result == result and conversation.accepted_offer_id == (
            offer_id if result is CallResult.ACUERDO else None
        )
        session.commit()
        return answer(None if same else Rejection.YA_REGISTRADO)

    offers = _call_offers(session, call, clock)
    rejection = check_registration(
        result,
        identity_verified=conversation.identity_verified,
        final_confirmation=final_confirmation,
        offer_id=offer_id,
        offered_ids=_progress(conversation, offers).offered_ids,
    )
    if rejection is not None:
        session.commit()  # guarda la conversación (y sus ofertas), no el resultado
        return answer(rejection)

    try:
        portfolio.record_call_outcome(
            session,
            company_id=call.company_id,
            case_id=call.case_id,
            status=CASE_STATUS_FOR_RESULT[result],
        )
    except ConflictError:
        session.rollback()
        return answer(Rejection.CASO_NO_NEGOCIABLE)

    now = clock.now()
    if result is CallResult.ACUERDO:
        assert offer_id is not None  # noqa: S101 - check_registration ya lo exigió
        agreement = _agreement(call, offers, offer_id, now)
        AgreementRepository(session).add(agreement)
        # El flujo anterior trae las fechas pactadas: las cuotas salen de ahí.
        add_installments(
            session, agreement, agreed_on=clock.today(), payment_days=DEFAULT_PAYMENT_DAYS
        )

    conversation.result = result.value
    conversation.accepted_offer_id = offer_id if result is CallResult.ACUERDO else None
    conversation.final_confirmation = final_confirmation
    conversation.unknown_count = unknown_count
    conversation.result_recorded_at = now
    conversation.status = "DONE"  # ya tiene resultado: no está "en curso"
    session.commit()
    return answer()


def _agreement(
    call: _Call, offers: CallOffers, offer_id: str, now: datetime
) -> PaymentAgreementModel:
    """El acuerdo con los números EXACTOS de la oferta que escuchó el deudor."""
    single, plan = offers.single_payment, offers.installments
    common = {
        "company_id": call.company_id,
        "case_id": call.case_id,
        "conversation_id": call.conversation.id,
        "offer_id": offer_id,
        "currency": offers.currency,
        "original_amount": offers.total_amount,
        "created_at": now,
    }
    if single is not None and single.offer_id == offer_id:
        return PaymentAgreementModel(
            **common,
            modality="PAGO_UNICO",
            total_amount=single.total_amount,
            installment_count=1,
            discount_pct=single.discount_pct,
            discount_amount=single.discount_amount,
            schedule=[
                {
                    "number": 1,
                    "due_date": single.pay_by.isoformat(),
                    "amount": str(single.total_amount),
                }
            ],
        )
    assert plan is not None and plan.offer_id == offer_id  # noqa: S101 - verificado antes
    return PaymentAgreementModel(
        **common,
        modality="CUOTAS",
        total_amount=plan.total_amount,
        installment_count=plan.installment_count,
        installment_amount=plan.installment_amount,
        schedule=[
            {"number": i.number, "due_date": i.due_date.isoformat(), "amount": str(i.amount)}
            for i in plan.schedule
        ],
    )
