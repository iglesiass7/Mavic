"""Contratos de las herramientas del agente de ElevenLabs.

LOS NOMBRES DE LOS CAMPOS los definió quien arma el agente (en español, con
estos nombres exactos). No se cambian sin cambiar también el agente.

Una diferencia a propósito con el resto de la API: acá los montos van como
NÚMERO JSON (120000, 53325.45), porque así los espera el agente. No se pierde
precisión que importe: son montos con 2 decimales que el agente solo lee en voz
alta. Adentro de Mavic siguen siendo Decimal exactos.

Campos agregados por Mavic que el agente todavía no usa (no rompen nada):
`motivo`, `fecha_limite_pago`, `fecha_primera_cuota`, `importe_ultima_cuota`,
`interes_porcentaje`.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

from mavic.modules.voice.application.agent_tools import (
    NO_OFFER_ID,
    CaseContext,
    InstallmentsAnswer,
    RegistrationAnswer,
    SinglePaymentAnswer,
)
from mavic.modules.voice.domain.outcomes import CallResult


def _as_json_number(value: Decimal) -> int | float:
    """120000.00 -> 120000 ; 53325.45 -> 53325.45 (como en los ejemplos del agente)."""
    return int(value) if value == value.to_integral_value() else float(value)


AgentAmount = Annotated[Decimal, PlainSerializer(_as_json_number, return_type=int | float)]

CaseReference = Annotated[str, Field(min_length=1, max_length=50, description="Número de caso")]
ConversationId = Annotated[
    str, Field(min_length=1, max_length=100, description="system__conversation_id de ElevenLabs")
]


# ---------------------------------------------------------------- entradas


class ContextIn(BaseModel):
    caso_id: CaseReference
    conversation_id: ConversationId
    nombre_consultado: str = Field(default="", max_length=200)
    respuesta: str | bool = Field(default="", description="Lo que contestó la persona")


class OfferIn(BaseModel):
    caso_id: CaseReference
    conversation_id: ConversationId


class ResultIn(BaseModel):
    caso_id: CaseReference
    conversation_id: ConversationId
    resultado: CallResult
    oferta_id: str | None = Field(default=None, max_length=40)
    confirmacion_final: bool = False
    cantidad_desconocimientos: int = Field(default=0, ge=0, le=100)


# ---------------------------------------------------------------- salidas


class DebtDetailsOut(BaseModel):
    nombre_acreedor: str
    contexto_deuda: str
    monto_original: AgentAmount
    moneda: str
    fecha_vencimiento_original: date


class ContextOut(BaseModel):
    caso_id: str
    nombre: str
    identidad_verificada: bool
    pago_unico_ofrecido: bool
    cuotas_ofrecidas: bool
    ofertas_restantes: int
    datos_comunicables: DebtDetailsOut | None

    @classmethod
    def from_context(cls, context: CaseContext) -> "ContextOut":
        debt = context.debt
        return cls(
            caso_id=context.case_reference,
            nombre=context.debtor_name,
            identidad_verificada=context.identity_verified,
            pago_unico_ofrecido=context.progress.single_offered,
            cuotas_ofrecidas=context.progress.installments_offered,
            ofertas_restantes=context.progress.remaining,
            datos_comunicables=None
            if debt is None
            else DebtDetailsOut(
                nombre_acreedor=debt.creditor_name,
                contexto_deuda=debt.debt_context,
                monto_original=debt.original_amount,
                moneda=debt.currency,
                fecha_vencimiento_original=debt.original_due_date,
            ),
        )


class SinglePaymentOut(BaseModel):
    has_offer: bool
    pago_unico_ofrecido: bool
    ofertas_restantes: int
    oferta_id: str
    modalidad: str = "PAGO_UNICO"
    moneda: str
    importe_original: AgentAmount
    descuento_porcentaje: AgentAmount
    descuento: AgentAmount
    importe_total: AgentAmount
    fecha_limite_pago: date | None
    motivo: str | None

    @classmethod
    def from_answer(cls, answer: SinglePaymentAnswer) -> "SinglePaymentOut":
        progress, offer = answer.progress, answer.offer
        common = {
            "pago_unico_ofrecido": progress.single_offered,
            "ofertas_restantes": progress.remaining,
            "moneda": progress.offers.currency,
            "motivo": answer.reason,
        }
        if offer is None:
            # Sin oferta: el mismo monto, sin descuento.
            return cls(
                has_offer=False,
                oferta_id=NO_OFFER_ID,
                importe_original=answer.fallback_amount,
                descuento_porcentaje=Decimal(0),
                descuento=Decimal(0),
                importe_total=answer.fallback_amount,
                fecha_limite_pago=None,
                **common,
            )
        return cls(
            has_offer=True,
            oferta_id=offer.offer_id,
            importe_original=offer.original_amount,
            descuento_porcentaje=offer.discount_pct,
            descuento=offer.discount_amount,
            importe_total=offer.total_amount,
            fecha_limite_pago=offer.pay_by,
            **common,
        )


class InstallmentsOut(BaseModel):
    has_offer: bool
    cuotas_ofrecidas: bool
    ofertas_restantes: int
    oferta_id: str
    modalidad: str = "CUOTAS"
    moneda: str
    importe_total: AgentAmount
    cantidad_cuotas: int
    importe_por_cuota: AgentAmount
    importe_ultima_cuota: AgentAmount
    interes_porcentaje: AgentAmount
    fecha_primera_cuota: date | None
    motivo: str | None

    @classmethod
    def from_answer(cls, answer: InstallmentsAnswer) -> "InstallmentsOut":
        progress, offer = answer.progress, answer.offer
        common = {
            "cuotas_ofrecidas": progress.installments_offered,
            "ofertas_restantes": progress.remaining,
            "moneda": progress.offers.currency,
            "motivo": answer.reason,
        }
        if offer is None:
            # Sin oferta: el mismo monto y 0 cuotas.
            return cls(
                has_offer=False,
                oferta_id=NO_OFFER_ID,
                importe_total=answer.fallback_amount,
                cantidad_cuotas=0,
                importe_por_cuota=Decimal(0),
                importe_ultima_cuota=Decimal(0),
                interes_porcentaje=Decimal(0),
                fecha_primera_cuota=None,
                **common,
            )
        return cls(
            has_offer=True,
            oferta_id=offer.offer_id,
            importe_total=offer.total_amount,
            cantidad_cuotas=offer.installment_count,
            importe_por_cuota=offer.installment_amount,
            importe_ultima_cuota=offer.schedule[-1].amount,
            interes_porcentaje=offer.interest_pct,
            fecha_primera_cuota=offer.schedule[0].due_date,
            **common,
        )


class ResultOut(BaseModel):
    registrado: bool
    resultado: CallResult
    oferta_id: str | None
    motivo: str | None

    @classmethod
    def from_answer(cls, answer: RegistrationAnswer) -> "ResultOut":
        return cls(
            registrado=answer.registered,
            resultado=answer.result,
            oferta_id=answer.offer_id,
            motivo=answer.rejection.value if answer.rejection else None,
        )
