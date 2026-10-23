import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OfferDetails } from "./OfferDetails";
import type { CaseOffers } from "@/lib/types";

// Copiado de una respuesta real de GET /cases/{id}/offers (caso demo de Ana Torres).
const WITH_INSTALLMENTS: CaseOffers = {
  case_id: "2eeffbe0-c89b-4416-a803-7b6085f3dcc1",
  case_number: 15,
  case_status: "pending",
  currency: "ARS",
  total_amount: "59250.50",
  debt_age_days: 42,
  invoice_count: 2,
  rule: { id: "9fc61e71-64b4-4f9f-96a4-cd79e01b7895", name: "Pago total corto plazo" },
  has_offer: true,
  reason: null,
  single_payment: {
    offer_id: "PAGO-UNICO",
    original_amount: "59250.50",
    discount_pct: "10.00",
    discount_amount: "5925.05",
    total_amount: "53325.45",
    pay_by: "2026-10-27",
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
      { number: 1, due_date: "2026-10-27", amount: "21330.18" },
      { number: 2, due_date: "2026-11-27", amount: "21330.18" },
      { number: 3, due_date: "2026-12-27", amount: "21330.18" },
    ],
  },
  call_offers: [
    {
      priority: 0,
      offer_id: "PAGO-UNICO",
      kind: "PAGO_UNICO",
      total_amount: "53325.45",
      discount_pct: "10.00",
      discount_amount: "5925.05",
      installment_count: 1,
      installment_amount: null,
    },
    {
      priority: 1,
      offer_id: "CUOTAS-3-CON-INTERES",
      kind: "CUOTAS",
      total_amount: "63990.54",
      discount_pct: null,
      discount_amount: null,
      installment_count: 3,
      installment_amount: "21330.18",
    },
  ],
};

// Testing Library normaliza los espacios (el que no corta pasa a ser uno común).
// Para comprobar el monto tal cual, se compara el texto crudo del elemento.
const money = (text: string) => screen.getByText((_, el) => el?.textContent === text);

describe("OfferDetails", () => {
  it("muestra la regla y las ofertas en el orden en que las presenta el agente", () => {
    render(<OfferDetails offers={WITH_INSTALLMENTS} />);

    expect(screen.getByText("Pago total corto plazo")).toBeInTheDocument();
    const titles = screen.getAllByText(/^\d\. /).map((el) => el.textContent);
    expect(titles).toEqual(["1. Pago único", "2. En cuotas"]);
    expect(money("$ 53.325,45")).toBeInTheDocument();
    expect(screen.getByText(/10\s%\sde descuento/)).toBeInTheDocument();
    expect(screen.getByText(/^3 × \$\s21\.330,18$/)).toBeInTheDocument();
    expect(screen.getByText(/\$\s63\.990,54 en total, cuotas iguales/)).toBeInTheDocument();
  });

  it("si la regla no permite cuotas, muestra solo el pago único", () => {
    const [single] = WITH_INSTALLMENTS.call_offers;
    render(<OfferDetails offers={{ ...WITH_INSTALLMENTS, call_offers: [single!] }} />);

    expect(screen.getByText("1. Pago único")).toBeInTheDocument();
    expect(screen.queryByText(/En cuotas/)).not.toBeInTheDocument();
  });

  it("sin descuento no inventa un 0 %", () => {
    const noDiscount = {
      ...WITH_INSTALLMENTS.call_offers[0]!,
      total_amount: "59250.50",
      discount_pct: null,
      discount_amount: null,
    };
    render(<OfferDetails offers={{ ...WITH_INSTALLMENTS, call_offers: [noDiscount] }} />);

    expect(screen.getByText("Sin descuento")).toBeInTheDocument();
    expect(screen.queryByText(/0\s%/)).not.toBeInTheDocument();
  });

  it("si el caso no se puede negociar, explica por qué", () => {
    render(
      <OfferDetails
        offers={{
          ...WITH_INSTALLMENTS,
          has_offer: false,
          rule: null,
          reason: "CASE_NOT_NEGOTIABLE",
          single_payment: null,
          installments: null,
          call_offers: [],
        }}
      />,
    );

    expect(screen.getByText(/ya tiene un resultado/i)).toBeInTheDocument();
  });
});
