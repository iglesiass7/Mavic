/**
 * Lo que el agente puede ofrecer hoy en un caso: pago único y cuotas.
 *
 * Los montos vienen calculados por el backend (GET /cases/{id}/offers): acá
 * solo se muestran. Son los mismos que recibe el agente de voz.
 */
import { formatDate, formatMoney, formatPercent } from "@/lib/format";
import { NO_OFFER_REASON_LABEL } from "@/lib/labels";
import type { CaseOffers } from "@/lib/types";

export function OfferDetails({ offers }: { offers: CaseOffers }) {
  if (!offers.has_offer || !offers.single_payment) {
    return (
      <p className="mt-3 text-sm">
        {offers.reason ? NO_OFFER_REASON_LABEL[offers.reason] : "No hay ofertas para este caso."}
      </p>
    );
  }
  const single = offers.single_payment;
  const plan = offers.installments;

  return (
    <div className="mt-3 space-y-5">
      {offers.rule && (
        <p className="text-sm text-muted">
          Según la regla <span className="font-medium text-ink">{offers.rule.name}</span>.
        </p>
      )}

      <div>
        <p className="text-sm font-medium">Pago único</p>
        <p className="text-2xl font-bold">{formatMoney(single.total_amount)}</p>
        <p className="text-sm text-muted">
          {single.discount_pct === "0.00"
            ? "Sin descuento"
            : `${formatPercent(single.discount_pct)} de descuento (${formatMoney(single.discount_amount)} menos)`}
          , pagando hasta el {formatDate(single.pay_by)}.
        </p>
      </div>

      <div>
        <p className="text-sm font-medium">En cuotas</p>
        {plan ? (
          <>
            <p className="text-2xl font-bold">
              {plan.installment_count} × {formatMoney(plan.installment_amount)}
            </p>
            <p className="text-sm text-muted">
              {plan.interest_pct === "0.00"
                ? "Sin interés"
                : `${formatPercent(plan.interest_pct)} de interés`}
              : {formatMoney(plan.total_amount)} en total. La primera vence el{" "}
              {formatDate(plan.schedule[0]?.due_date ?? single.pay_by)}.
            </p>
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-petrol">Ver el cronograma</summary>
              <ol className="mt-2 space-y-1">
                {plan.schedule.map((installment) => (
                  <li key={installment.number} className="flex justify-between gap-4">
                    <span>
                      Cuota {installment.number} · {formatDate(installment.due_date)}
                    </span>
                    <span>{formatMoney(installment.amount)}</span>
                  </li>
                ))}
              </ol>
            </details>
          </>
        ) : (
          <p className="text-sm text-muted">La regla de este caso no permite cuotas.</p>
        )}
      </div>
    </div>
  );
}
