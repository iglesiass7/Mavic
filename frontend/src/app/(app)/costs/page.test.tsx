/** El medidor de costos con una respuesta como la de GET /costs. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CostsPage from "./page";
import type { CostRates, MonthCosts } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/costs",
  useSearchParams: () => new URLSearchParams("mes=2026-10"),
}));

const ME = {
  user: { id: "u1", name: "Martín Ruiz", role: "supervisor" },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "view_audit", "view_costs"],
};

const RATES: CostRates = {
  currency: "USD",
  call_minute: "0.1200",
  email: "0.0010",
  whatsapp: "0.0500",
  monthly_budget: "50.00",
  configured: true,
};

const COSTS: MonthCosts = {
  month: "2026-10",
  currency: "USD",
  rates_configured: true,
  days_in_month: 31,
  days_counted: 23,
  concepts: [
    { concept: "calls", quantity: "5.80", count: 4, rate: "0.1200", cost: "0.70", projected_cost: "0.94" },
    { concept: "email", quantity: "18.00", count: 18, rate: "0.0010", cost: "0.02", projected_cost: "0.03" },
    { concept: "whatsapp", quantity: "0.00", count: 0, rate: "0.0500", cost: "0.00", projected_cost: "0.00" },
  ],
  total: "0.72",
  projected_total: "0.97",
  monthly_budget: "50.00",
  budget_status: "ok",
  daily: Array.from({ length: 31 }, (_, i) => ({
    day: `2026-10-${String(i + 1).padStart(2, "0")}`,
    cost: i === 21 ? "0.70" : "0.00",
  })),
};

function backend() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.startsWith("/api/costs") ? COSTS : url.startsWith("/api/cost-rates") ? RATES : ME;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }),
      );
    }),
  );
}

describe("Medidor de costos", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra el uso, las tarifas y los totales tal como vienen del backend", async () => {
    backend();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CostsPage />
      </QueryClientProvider>,
    );

    const table = await screen.findByRole("table", { name: "Costos por concepto" });
    const calls = within(table).getByRole("row", { name: /Llamadas del agente/ });
    expect(calls).toHaveTextContent("5,8 min · 4 llamadas");
    expect(calls).toHaveTextContent(/USD\s0,1200 por minuto/);
    expect(within(table).getByRole("row", { name: /Total/ })).toHaveTextContent(/USD\s0,72.*USD\s0,97/);
    expect(screen.getByText(/Consumo dentro del tope/)).toBeInTheDocument();
    // El supervisor ve los costos pero no cambia las tarifas.
    expect(screen.queryByRole("button", { name: /Editar tarifas/ })).not.toBeInTheDocument();
  });
});
