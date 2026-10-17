"""Las ofertas de UNA llamada y cuáles ya se le dijeron al deudor.

Las ofertas se calculan la primera vez que el agente las necesita y quedan
FIJAS durante toda la llamada. Si a mitad de la llamada un administrador cambia
una regla, el deudor no escucha un número y después se registra otro.

El agente presenta primero el pago único y, si no alcanza, las cuotas:

    ofertas disponibles: pago único + cuotas      -> ofertas_restantes = 2
    el agente pide el pago único                  -> ofertas_restantes = 1
    el agente pide las cuotas                     -> ofertas_restantes = 0
"""

from dataclasses import dataclass
from decimal import Decimal

from mavic.modules.negotiation.domain.offers import InstallmentsOffer, SinglePaymentOffer


@dataclass(frozen=True)
class CallOffers:
    total_amount: Decimal  # deuda del caso al momento de calcular
    currency: str
    rule_name: str | None
    no_offer_reason: str | None  # por qué no hay ofertas, si no las hay
    single_payment: SinglePaymentOffer | None
    installments: InstallmentsOffer | None


@dataclass(frozen=True)
class OfferProgress:
    offers: CallOffers
    single_offered: bool
    installments_offered: bool

    @property
    def remaining(self) -> int:
        """Cuántas ofertas quedan por presentar en esta llamada."""
        pending = [
            self.offers.single_payment is not None and not self.single_offered,
            self.offers.installments is not None and not self.installments_offered,
        ]
        return sum(pending)

    @property
    def offered_ids(self) -> frozenset[str]:
        """Las ofertas que el deudor ya escuchó: solo esas se pueden aceptar."""
        ids = set()
        if self.single_offered and self.offers.single_payment:
            ids.add(self.offers.single_payment.offer_id)
        if self.installments_offered and self.offers.installments:
            ids.add(self.offers.installments.offer_id)
        return frozenset(ids)
