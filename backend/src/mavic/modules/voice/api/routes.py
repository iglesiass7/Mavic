"""Endpoints para las personas de la empresa: las llamadas de un caso.

Requieren sesión y el permiso VIEW_PORTFOLIO (administrador, operador, supervisor).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.modules.voice.application.conversations import (
    AgreementView,
    ConversationView,
    list_case_conversations,
)

router = APIRouter(tags=["agent"])


class AgreementOut(BaseModel):
    offer_id: str
    modality: str
    currency: str
    original_amount: Decimal
    total_amount: Decimal
    installment_count: int
    schedule: list[dict[str, Any]]
    created_at: datetime

    @classmethod
    def from_view(cls, view: AgreementView) -> "AgreementOut":
        return cls(**view.__dict__)


class ConversationOut(BaseModel):
    id: UUID
    provider_conversation_id: str
    started_at: datetime
    identity_verified: bool
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
