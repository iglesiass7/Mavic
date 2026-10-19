import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OfferDetails } from "./OfferDetails";
import type { CaseOffers } from "@/lib/types";

// Copiado de una respuesta real de GET /cases/{id}/offers (caso demo de Ana Torres).
const WITH_INSTALLMENTS: CaseOffers = {
  case_id: "a44dd2e0-2e5f-423b-b717-e71911b0860c",
  case_number: 3,
  case_status: "pending",
  currency: "ARS",
  total_amount: "59250.50",
  debt_age_days: 39,
  invoice_count: 2,
  rule: { id: "aa71dfd4-184f-48cd-a048-1b9523a9159d", name: "Pago total corto plazo" },
  has_offer: true,
  reason: null,
  single_payment: {
    offer_id: "PAGO-UNICO",
    original_amount: "59250.50",
    discount_pct: "10.00",
    discount_amount: "5925.05",
    total_amount: "53325.45",
    pay_by: "2026-10-24",
  },
  installments: {
    offer_id: "CUOTAS-3-CON-INTERES",
    original_amount: "59250.50",
    interest_pct: "8.00",
    interest_amount: "4740.04",
    total_amount: "63990.54",
    installment_count: 3,
    installment_amount: "21330.18",
    schedule: [
      { number: 1, due_date: "2026-10-24", amount: "21330.18" },
      { number: 2, due_date: "2026-11-24", amount: "21330.18" },
      { number: 3, due_date: "2026-12-24", amount: "21330.18" },
    ],
  },
};

// Testing Library normaliza los espacios (el que no corta pasa a ser uno común).
// Para comprobar el monto tal cual, se compara el texto crudo del elemento.
const money = (text: string) => screen.getByText((_, el) => el?.textContent === text);

describe("OfferDetails", () => {
  it("muestra la regla, el pago único y las cuotas con los montos del backend", () => {
    render(<OfferDetails offers={WITH_INSTALLMENTS} />);

    expect(screen.getByText("Pago total corto plazo")).toBeInTheDocument();
    expect(money("$\u00a053.325,45")).toBeInTheDocument();
    expect(screen.getByText(/10\s%\sde descuento/)).toBeInTheDocument();
    expect(screen.getByText(/^3 × \$\s21\.330,18$/)).toBeInTheDocument();
    expect(screen.getByText(/8\s%\sde interés: \$\s63\.990,54 en total/)).toBeInTheDocument();
    expect(screen.getByText("Cuota 3 · 24/12/2026")).toBeInTheDocument();
  });

  it("si la regla no permite cuotas, lo dice", () => {
    render(<OfferDetails offers={{ ...WITH_INSTALLMENTS, installments: null }} />);

    expect(screen.getByText("La regla de este caso no permite cuotas.")).toBeInTheDocument();
  });

  it("sin descuento no inventa un 0 %", () => {
    const offers: CaseOffers = {
      ...WITH_INSTALLMENTS,
      single_payment: {
        ...WITH_INSTALLMENTS.single_payment!,
        discount_pct: "0.00",
        discount_amount: "0.00",
        total_amount: "59250.50",
      },
    };
    render(<OfferDetails offers={offers} />);

    expect(screen.getByText(/Sin descuento/)).toBeInTheDocument();
    expect(screen.queryByText(/\b0\s%/)).not.toBeInTheDocument();
  });

  it("si el caso no se puede negociar, explica por qué", () => {
    const offers: CaseOffers = {
      ...WITH_INSTALLMENTS,
      case_status: "agreement",
      rule: null,
      has_offer: false,
      reason: "CASE_NOT_NEGOTIABLE",
      single_payment: null,
      installments: null,
    };
    render(<OfferDetails offers={offers} />);

    expect(screen.getByText(/ya tiene un resultado/)).toBeInTheDocument();
    expect(screen.queryByText("Pago único")).not.toBeInTheDocument();
  });
});
