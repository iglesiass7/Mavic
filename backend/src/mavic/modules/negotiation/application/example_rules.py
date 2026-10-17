"""Reglas de ejemplo para la empresa de demostración.

FUENTE: son las cuatro reglas por defecto del sistema original (rule_seed.py),
con los mismos rangos y porcentajes. Cambios:
- "Sin tope" es un máximo vacío en vez de 9999 días o 999.999.999 pesos.
- La cuarta regla arranca en 500.000,01 (el original usaba 500.001 porque solo
  manejaba pesos enteros).
- Se corrigieron tildes en nombres y descripciones.

Hay un hueco a propósito, igual que en el original: una deuda de más de 500.000
con menos de 15 días de atraso no tiene regla, y por lo tanto no tiene oferta.
"""

from decimal import Decimal

from mavic.modules.negotiation.application.rules import RuleData
from mavic.modules.negotiation.domain.rules import Interval, PaymentTerms, RuleConditions

UP_TO_500K = Interval(Decimal("0"), Decimal("500000"))
UP_TO_12_INVOICES = Interval(1, 12)

EXAMPLE_RULES = (
    RuleData(
        name="Deuda reciente sin descuento",
        description="Mora menor a 15 días: gestión conservadora, solo pago total y sin descuento.",
        conditions=RuleConditions(UP_TO_500K, Interval(0, 14), UP_TO_12_INVOICES),
        terms=PaymentTerms(
            discount_pct=Decimal("0"), payment_days=5, max_installments=1, interest_pct=Decimal("0")
        ),
    ),
    RuleData(
        name="Pago total corto plazo",
        description="Mora de 15 a 59 días: descuento por pago total o hasta 3 cuotas.",
        conditions=RuleConditions(UP_TO_500K, Interval(15, 59), UP_TO_12_INVOICES),
        terms=PaymentTerms(
            discount_pct=Decimal("10"),
            payment_days=5,
            max_installments=3,
            interest_pct=Decimal("8"),
        ),
    ),
    RuleData(
        name="Mora alta con plan extendido",
        description="Mora desde 60 días: hasta 6 cuotas y plazo corto para el primer pago.",
        conditions=RuleConditions(UP_TO_500K, Interval(60, None), UP_TO_12_INVOICES),
        terms=PaymentTerms(
            discount_pct=Decimal("10"),
            payment_days=5,
            max_installments=6,
            interest_pct=Decimal("12"),
        ),
    ),
    RuleData(
        name="Deuda alta con descuento adicional",
        description="Deudas de más de 500.000 con mora avanzada: más descuento y financiación.",
        conditions=RuleConditions(
            Interval(Decimal("500000.01"), None), Interval(15, None), Interval(1, None)
        ),
        terms=PaymentTerms(
            discount_pct=Decimal("15"),
            payment_days=5,
            max_installments=6,
            interest_pct=Decimal("18"),
        ),
    ),
)
