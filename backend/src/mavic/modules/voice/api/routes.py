"""Endpoints para las personas de la empresa: las llamadas de un caso.

- GET  /conversations              todas las llamadas de la empresa (VIEW_PORTFOLIO)
- GET  /cases/{id}/conversations   las llamadas de un caso (VIEW_PORTFOLIO: todos los roles)
- POST /cases/{id}/calls           llamar al deudor con el agente (OPERATE_PORTFOLIO)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel

from mavic.api.deps import ActorDep, ClockDep, SessionDep, SettingsDep
from mavic.api.pagination import Limit, Offset, PageOut
from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.voice.application.calls import CallSettings, StartedCall, start_debt_call
from mavic.modules.voice.application.conversations import (
    AgreementView,
    CallListItem,
    CallOutcomeFilter,
    ConversationView,
    list_case_conversations,
    list_company_calls,
)
from mavic.modules.voice.domain.call_gateway import CallGateway

router = APIRouter(tags=["agent"])


def get_call_gateway(request: Request) -> CallGateway | None:
    """El cliente de ElevenLabs que armó la app al arrancar (None si faltan datos)."""
    gateway: CallGateway | None = request.app.state.call_gateway
    return gateway


CallGatewayDep = Annotated[CallGateway | None, Depends(get_call_gateway)]


class AgreementOut(BaseModel):
    offer_id: str
    modality: str
    currency: str
    original_amount: Decimal
    total_amount: Decimal
    installment_count: int
    installment_amount: Decimal | None
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    schedule: list[dict[str, Any]] | None
    created_at: datetime

    @classmethod
    def from_view(cls, view: AgreementView) -> "AgreementOut":
        return cls(**view.__dict__)


class ConversationOut(BaseModel):
    id: UUID
    provider_conversation_id: str | None
    origin: str
    status: str
    failure_reason: str | None
    review_reason: str | None
    started_at: datetime
    identity_verified: bool | None
    offered: list[str]
    result: str | None
    unknown_count: int | None
    agreement: AgreementOut | None
    summary: str | None
    call_duration_secs: int | None
    transcript: list[dict[str, Any]] | None

    @classmethod
    def from_view(cls, view: ConversationView) -> "ConversationOut":
        data = dict(view.__dict__)
        data["agreement"] = AgreementOut.from_view(view.agreement) if view.agreement else None
        return cls(**data)


@router.get("/cases/{case_id}/conversations")
def case_conversations(
    case_id: UUID, session: SessionDep, actor: ActorDep, clock: ClockDep
) -> list[ConversationOut]:
    """Llamadas del caso: identidad, ofertas presentadas, resultado, acuerdo y transcripción."""
    views = list_case_conversations(session, actor=actor, clock=clock, case_id=case_id)
    return [ConversationOut.from_view(view) for view in views]


class StartedCallOut(BaseModel):
    conversation_id: UUID
    status: str
    provider_conversation_id: str | None
    provider_call_sid: str | None

    @classmethod
    def from_view(cls, view: StartedCall) -> "StartedCallOut":
        return cls(**view.__dict__)


@router.post("/cases/{case_id}/calls", status_code=status.HTTP_201_CREATED)
def start_call(
    case_id: UUID,
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    settings: SettingsDep,
    gateway: CallGatewayDep,
) -> StartedCallOut:
    """Llama al deudor con el agente (ADR-034). El resultado llega después, por el webhook.

    Errores: 409 si el caso ya tiene resultado, si hay otra llamada en curso o si
    ninguna regla se aplica; 503 si faltan las credenciales de ElevenLabs o si
    ElevenLabs no pudo iniciar la llamada.
    """
    call_settings = (
        CallSettings(agent_id=settings.elevenlabs_agent_id, branch_id=settings.elevenlabs_branch_id)
        if settings.elevenlabs_agent_id
        else None
    )
    view = start_debt_call(
        session,
        actor=actor,
        clock=clock,
        gateway=gateway,
        call_settings=call_settings,
        case_id=case_id,
    )
    return StartedCallOut.from_view(view)


class CallListItemOut(BaseModel):
    call: ConversationOut
    case_id: UUID
    case_number: int
    case_status: CaseStatus
    debtor_name: str

    @classmethod
    def from_item(cls, item: CallListItem) -> "CallListItemOut":
        return cls(
            call=ConversationOut.from_view(item.conversation),
            case_id=item.case_id,
            case_number=item.case_number,
            case_status=item.case_status,
            debtor_name=item.debtor_name,
        )


@router.get("/conversations")
def company_calls(
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    limit: Limit = 50,
    offset: Offset = 0,
    outcome: Annotated[
        CallOutcomeFilter | None,
        Query(description="ongoing, review, failed o un resultado (CONTACTADO, ACUERDO...)"),
    ] = None,
    day: Annotated[date | None, Query(description="Solo las de ese día (hora argentina)")] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Deudor, DNI o número de caso")
    ] = None,
) -> PageOut[CallListItemOut]:
    """Todas las llamadas de la empresa, de la más nueva a la más vieja."""
    page = list_company_calls(
        session,
        actor=actor,
        clock=clock,
        outcome=outcome,
        day=day,
        search=q,
        limit=limit,
        offset=offset,
    )
    return PageOut(
        items=[CallListItemOut.from_item(i) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )
