/**
 * Lo que el agente le ofrece al deudor si se lo llama hoy, en el orden en que
 * lo presenta (ADR-034). Los montos vienen calculados por el backend
 * (GET /cases/{id}/offers, `call_offers`): son los MISMOS que recibe el agente.
 */
import { formatMoney, formatPercent } from "@/lib/format";
import { NO_OFFER_REASON_LABEL } from "@/lib/labels";
import type { CallOffer, CaseOffers } from "@/lib/types";

export function OfferDetails({ offers }: { offers: CaseOffers }) {
  if (offers.call_offers.length === 0) {
    return (
      <p className="text-sm">
        {offers.reason ? NO_OFFER_REASON_LABEL[offers.reason] : "No hay ofertas para este caso."}
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {offers.rule && (
        <p className="text-sm text-muted">
          Según la regla <span className="font-semibold text-ink">{offers.rule.name}</span>. El
          agente las presenta en este orden.
        </p>
      )}
      <ol className="space-y-3">
        {offers.call_offers.map((offer) => (
          <li key={offer.offer_id} className="rounded-2xl border border-line bg-white px-4 py-3">
            <OfferLine offer={offer} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function OfferLine({ offer }: { offer: CallOffer }) {
  const position = `${offer.priority + 1}.`;
  if (offer.kind === "PAGO_UNICO") {
    return (
      <>
        <p className="text-xs font-bold text-muted">{position} Pago único</p>
        <p className="mt-0.5 text-xl font-bold tabular">{formatMoney(offer.total_amount)}</p>
        <p className="text-xs text-muted">
          {offer.discount_pct && offer.discount_amount
            ? `${formatPercent(offer.discount_pct)} de descuento (${formatMoney(offer.discount_amount)} menos)`
            : "Sin descuento"}
        </p>
      </>
    );
  }
  return (
    <>
      <p className="text-xs font-bold text-muted">{position} En cuotas</p>
      <p className="mt-0.5 text-xl font-bold tabular">
        {offer.installment_count} × {formatMoney(offer.installment_amount ?? "0")}
      </p>
      <p className="text-xs text-muted">{formatMoney(offer.total_amount)} en total, cuotas iguales</p>
    </>
  );
}
