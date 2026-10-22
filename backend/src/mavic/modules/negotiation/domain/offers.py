"""Cálculo de las ofertas de pago a partir de una regla.

El agente de voz NO calcula: le pide la oferta al backend y la comunica. Así un
cálculo mal hecho (o un "descuento" inventado por la IA) no llega al deudor.

Dos ofertas posibles, en el orden en que las presenta el agente:

    1. PAGO ÚNICO   deuda - descuento, a pagar dentro del plazo
                    120.000 con 10 % -> 108.000
    2. CUOTAS       deuda + interés, en N cuotas mensuales
                    120.000 en 3 cuotas sin interés -> 3 x 40.000

Los identificadores (`PAGO-UNICO`, `CUOTAS-3-SIN-INTERES`) son los que usa el
agente de ElevenLabs, para que pueda decir qué oferta aceptó el deudor.

PLATA: siempre Decimal y redondeo "half up" a centavos (el redondeo que se
enseña en la escuela: 0,005 -> 0,01). Nunca float.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import StrEnum

from mavic.modules.negotiation.domain.rules import PaymentTerms

CENT = Decimal("0.01")
SINGLE_PAYMENT_ID = "PAGO-UNICO"


@dataclass(frozen=True)
class SinglePaymentOffer:
    offer_id: str
    original_amount: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    pay_by: date  # fecha límite para pagar


@dataclass(frozen=True)
class Installment:
    number: int
    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class InstallmentsOffer:
    offer_id: str
    original_amount: Decimal
    interest_pct: Decimal
    interest_amount: Decimal
    total_amount: Decimal
    installment_count: int
    installment_amount: Decimal  # monto de cada cuota (la última puede tener unos centavos más)
    schedule: list[Installment]


@dataclass(frozen=True)
class Offers:
    single_payment: SinglePaymentOffer
    installments: InstallmentsOffer | None  # None si la regla permite una sola cuota


def to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, pct: Decimal) -> Decimal:
    """Porcentaje de un monto, redondeado a centavos.

    >>> percent_of(Decimal("120000"), Decimal("10"))
    Decimal('12000.00')
    """
    return to_cents(amount * pct / 100)


def add_months(start: date, months: int) -> date:
    """Mismo día N meses después; si ese mes es más corto, el último día del mes.

    >>> add_months(date(2026, 1, 31), 1)
    datetime.date(2026, 2, 28)
    """
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def split_in_installments(total: Decimal, count: int) -> list[Decimal]:
    """Divide un total en cuotas que suman EXACTO el total.

    100 en 3 cuotas: 33,33 + 33,33 + 33,34. Las primeras se redondean para abajo
    y la última se lleva los centavos que sobran. Si se redondearan todas igual,
    3 x 33,33 = 99,99 y se perdería un centavo.
    """
    regular = (total / count).quantize(CENT, rounding=ROUND_DOWN)
    return [regular] * (count - 1) + [total - regular * (count - 1)]


def installments_offer_id(count: int, interest_pct: Decimal) -> str:
    """Identificador de la oferta en cuotas, con el formato que usa el agente.

    >>> installments_offer_id(3, Decimal("0"))
    'CUOTAS-3-SIN-INTERES'
    """
    return f"CUOTAS-{count}-{'SIN' if interest_pct == 0 else 'CON'}-INTERES"


def single_payment_offer(terms: PaymentTerms, debt: Decimal, today: date) -> SinglePaymentOffer:
    discount = percent_of(debt, terms.discount_pct)
    return SinglePaymentOffer(
        offer_id=SINGLE_PAYMENT_ID,
        original_amount=debt,
        discount_pct=terms.discount_pct,
        discount_amount=discount,
        total_amount=debt - discount,
        pay_by=today + timedelta(days=terms.payment_days),
    )


def installments_offer(terms: PaymentTerms, debt: Decimal, today: date) -> InstallmentsOffer | None:
    """Plan con el máximo de cuotas que permite la regla. Las cuotas no tienen descuento:
    el descuento es el premio por pagar todo junto."""
    count = terms.max_installments
    if count < 2:
        return None
    interest = percent_of(debt, terms.interest_pct)
    total = debt + interest
    first_due = today + timedelta(days=terms.payment_days)
    amounts = split_in_installments(total, count)
    return InstallmentsOffer(
        offer_id=installments_offer_id(count, terms.interest_pct),
        original_amount=debt,
        interest_pct=terms.interest_pct,
        interest_amount=interest,
        total_amount=total,
        installment_count=count,
        installment_amount=amounts[0],
        schedule=[
            Installment(number=i + 1, due_date=add_months(first_due, i), amount=amount)
            for i, amount in enumerate(amounts)
        ],
    )


def build_offers(terms: PaymentTerms, debt: Decimal, today: date) -> Offers:
    return Offers(
        single_payment=single_payment_offer(terms, debt, today),
        installments=installments_offer(terms, debt, today),
    )


# ---------------------------------------------------------------- contrato de llamada (ADR-034)
#
# Para las llamadas que inicia Mavic, el agente recibe TODAS las ofertas antes
# de empezar, en una lista ordenada: primero la posición 0, después la 1. No
# hay fechas (el agente no pacta fechas de pago) y cada plan en cuotas tiene
# UN solo importe por cuota: todas las cuotas son iguales.


class OfferKind(StrEnum):
    SINGLE_PAYMENT = "PAGO_UNICO"
    INSTALLMENTS = "CUOTAS"


@dataclass(frozen=True)
class CallOffer:
    """Una oferta tal como la recibe el agente (y como queda en la foto de la llamada)."""

    priority: int  # posición en la lista: 0 se presenta primero
    offer_id: str
    kind: OfferKind
    total_amount: Decimal  # lo que el deudor se compromete a pagar en total
    discount_pct: Decimal | None  # solo pago único con descuento
    discount_amount: Decimal | None
    installment_count: int  # 1 en el pago único
    installment_amount: Decimal | None  # solo cuotas: el importe de CADA cuota


def equal_installment(total: Decimal, count: int) -> Decimal:
    """Importe de cada cuota cuando todas tienen que ser iguales.

    Se redondea al centavo más cercano y el total del plan pasa a ser
    cuotas x importe. Así lo que dice el agente ("6 cuotas de 57.866,67")
    multiplica EXACTO el total que se registra, sin una última cuota distinta.
    La diferencia con la cuenta sin redondear es menor a medio centavo por cuota.

    >>> equal_installment(Decimal("347200"), 6)
    Decimal('57866.67')
    """
    return to_cents(total / count)


def call_offer_list(terms: PaymentTerms, debt: Decimal) -> list[CallOffer]:
    """Las ofertas de una regla para una deuda, en el orden en que se presentan.

    >>> from mavic.modules.negotiation.domain.rules import PaymentTerms
    >>> terms = PaymentTerms(discount_pct=Decimal("10"), payment_days=5,
    ...     max_installments=6, interest_pct=Decimal("12"))
    >>> for o in call_offer_list(terms, Decimal("310000")):
    ...     print(o.priority, o.offer_id, o.total_amount, o.installment_amount)
    0 PAGO-UNICO 279000.00 None
    1 CUOTAS-6-CON-INTERES 347200.02 57866.67
    """
    discount = percent_of(debt, terms.discount_pct)
    offers = [
        CallOffer(
            priority=0,
            offer_id=SINGLE_PAYMENT_ID,
            kind=OfferKind.SINGLE_PAYMENT,
            total_amount=to_cents(debt - discount),
            discount_pct=terms.discount_pct if terms.discount_pct > 0 else None,
            discount_amount=discount if terms.discount_pct > 0 else None,
            installment_count=1,
            installment_amount=None,
        )
    ]
    count = terms.max_installments
    if count >= 2:
        installment = equal_installment(debt + percent_of(debt, terms.interest_pct), count)
        offers.append(
            CallOffer(
                priority=1,
                offer_id=installments_offer_id(count, terms.interest_pct),
                kind=OfferKind.INSTALLMENTS,
                total_amount=installment * count,
                discount_pct=None,
                discount_amount=None,
                installment_count=count,
                installment_amount=installment,
            )
        )
    return offers
