"""Reglas de negociación: A QUÉ deudas se aplican y QUÉ se puede ofrecer.

Una regla tiene dos partes:

    CONDICIONES (¿a qué casos se aplica?)       CONDICIONES DE PAGO (¿qué se ofrece?)
    - monto total de la deuda: entre X e Y      - % de descuento si paga todo junto
    - días de atraso:          entre X e Y      - días de plazo para pagar
    - cantidad de facturas:    entre X e Y      - máximo de cuotas
                                                - % de interés del plan en cuotas

Ejemplo (una de las reglas de ejemplo que traía el sistema original):

    "Mora alta con plan extendido"
    monto 0 a 500.000, 60 días de atraso o más, 1 a 12 facturas
    -> 10 % de descuento por pago único, o hasta 6 cuotas con 12 % de interés

DIFERENCIAS CON EL ORIGINAL
- El backend DECIDE la oferta (antes devolvía varias reglas y elegía el agente).
  Para eso, a cada caso le tiene que corresponder UNA sola regla: dos reglas
  activas no pueden tener condiciones que se pisen (ver `conditions_overlap`).
- "Sin tope" es un máximo vacío (None), no un número mágico como 9999.

Este archivo no sabe nada de bases de datos ni de HTTP: son reglas puras.
"""

from dataclasses import dataclass
from decimal import Decimal

from mavic.core.errors import BusinessRuleViolationError

# Límites de sentido común (decisión propia, fáciles de cambiar). El original
# solo exigía "1 cuota o más" y "1 día o más", sin techo.
MAX_INSTALLMENTS = 36
MAX_PAYMENT_DAYS = 90
MAX_PERCENT = Decimal("100")


@dataclass(frozen=True)
class Interval[T: (int, Decimal)]:
    """Un rango con los dos extremos incluidos. `maximum=None` significa "sin tope".

    >>> Interval(60, None).contains(400)
    True
    >>> Interval(0, 14).contains(15)
    False
    """

    minimum: T
    maximum: T | None = None

    def contains(self, value: T) -> bool:
        return self.minimum <= value and (self.maximum is None or value <= self.maximum)

    def overlaps(self, other: "Interval[T]") -> bool:
        """¿Hay algún valor que esté en los dos rangos?

        [0, 14] y [15, 59] no se pisan. [0, 500000] y [500000, None] sí: comparten 500000.
        """
        starts_before_other_ends = other.maximum is None or self.minimum <= other.maximum
        other_starts_before_self_ends = self.maximum is None or other.minimum <= self.maximum
        return starts_before_other_ends and other_starts_before_self_ends


@dataclass(frozen=True)
class RuleConditions:
    amount: Interval[Decimal]
    debt_age_days: Interval[int]
    invoice_count: Interval[int]


@dataclass(frozen=True)
class PaymentTerms:
    discount_pct: Decimal  # descuento si paga todo junto
    payment_days: int  # plazo para el pago único y para la primera cuota
    max_installments: int  # 1 = solo pago único, sin plan en cuotas
    interest_pct: Decimal  # interés total del plan en cuotas


@dataclass(frozen=True)
class CaseFacts:
    """Lo que hace falta saber de un caso para elegir su regla."""

    total_amount: Decimal
    debt_age_days: int
    invoice_count: int


# ---------------------------------------------------------------- validación


def _invalid(field: str, message: str, code: str) -> BusinessRuleViolationError:
    return BusinessRuleViolationError(message, code=code, details={"field": field})


def _validate_interval[T: (int, Decimal)](field: str, interval: Interval[T], lowest: T) -> None:
    if interval.minimum < lowest:
        raise _invalid(
            field, f"El mínimo de {field} no puede ser menor que {lowest}.", "INVALID_RANGE"
        )
    if interval.maximum is not None and interval.maximum < interval.minimum:
        raise _invalid(field, f"En {field}, el máximo es menor que el mínimo.", "INVALID_RANGE")


def validate_conditions(conditions: RuleConditions) -> None:
    _validate_interval("amount", conditions.amount, Decimal("0"))
    _validate_interval("debt_age_days", conditions.debt_age_days, 0)
    _validate_interval("invoice_count", conditions.invoice_count, 1)


def validate_terms(terms: PaymentTerms) -> None:
    # 100 % de descuento sería perdonar la deuda, no un pago: no es una oferta.
    if not Decimal("0") <= terms.discount_pct < MAX_PERCENT:
        raise _invalid(
            "discount_pct", "El descuento tiene que estar entre 0 y 99,99 %.", "INVALID_DISCOUNT"
        )
    if not Decimal("0") <= terms.interest_pct <= MAX_PERCENT:
        raise _invalid(
            "interest_pct", "El interés tiene que estar entre 0 y 100 %.", "INVALID_INTEREST"
        )
    if not 1 <= terms.max_installments <= MAX_INSTALLMENTS:
        raise _invalid(
            "max_installments",
            f"Las cuotas tienen que estar entre 1 y {MAX_INSTALLMENTS}.",
            "INVALID_INSTALLMENTS",
        )
    if not 1 <= terms.payment_days <= MAX_PAYMENT_DAYS:
        raise _invalid(
            "payment_days",
            f"El plazo para pagar tiene que estar entre 1 y {MAX_PAYMENT_DAYS} días.",
            "INVALID_PAYMENT_DAYS",
        )


# ---------------------------------------------------------------- elección de regla


def applies_to(conditions: RuleConditions, facts: CaseFacts) -> bool:
    """¿Esta regla se aplica a este caso? Tienen que cumplirse las tres condiciones."""
    return (
        conditions.amount.contains(facts.total_amount)
        and conditions.debt_age_days.contains(facts.debt_age_days)
        and conditions.invoice_count.contains(facts.invoice_count)
    )


def conditions_overlap(a: RuleConditions, b: RuleConditions) -> bool:
    """¿Existe algún caso al que se le apliquen las dos reglas?

    Solo si se pisan los TRES rangos a la vez. Ejemplo: dos reglas con el mismo
    rango de monto pero distintos días de atraso ([0, 14] y [15, 59]) no se pisan:
    ningún caso puede tener 14 y 15 días de atraso al mismo tiempo.
    """
    return (
        a.amount.overlaps(b.amount)
        and a.debt_age_days.overlaps(b.debt_age_days)
        and a.invoice_count.overlaps(b.invoice_count)
    )
