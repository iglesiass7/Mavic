/** El tablero con una respuesta real de GET /dashboard (la de la prueba con los datos demo). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./page";
import type { Dashboard } from "@/lib/types";

const ME = {
  user: { id: "u1", name: "Laura Gómez", role: "admin" },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "operate_portfolio"],
};

const DATA: Dashboard = {
  as_of: "2026-10-19",
  portfolio: {
    currency: "ARS",
    cases_total: 4,
    amount_total: "167650.50",
    by_status: [
      { key: "pending", cases: 2, amount: "51500.00" },
      { key: "contacted", cases: 1, amount: "56900.00" },
      { key: "agreement", cases: 1, amount: "59250.50" },
      { key: "disputed", cases: 0, amount: "0.00" },
      { key: "escalated", cases: 0, amount: "0.00" },
      { key: "closed", cases: 0, amount: "0.00" },
    ],
    in_progress_cases: 3,
    in_progress_amount: "108400.00",
    in_progress_by_age: [
      { key: "0_30", cases: 1, amount: "19900.00" },
      { key: "31_60", cases: 0, amount: "0.00" },
      { key: "61_90", cases: 1, amount: "56900.00" },
      { key: "91_plus", cases: 1, amount: "31600.00" },
    ],
    unassigned_overdue_invoices: 0,
    unassigned_overdue_amount: "0.00",
    upcoming_invoices: 2,
    upcoming_amount: "39800.00",
  },
  agent: {
    calls: 3,
    identity_verified: 2,
    calls_by_result: { CONTACTADO: 1, DESCONOCIMIENTO: 0, ACUERDO: 1, DERIVACION_HUMANA: 0 },
    calls_without_result: 1,
    last_call_at: "2026-10-19T21:35:06Z",
    agreements: 1,
    agreements_single_payment: 0,
    agreements_installments: 1,
    agreed_original_amount: "59250.50",
    agreed_amount: "63990.54",
  },
  payments: {
    active: 1,
    fulfilled: 0,
    late: 0,
    collected_amount: "21330.18",
    pending_amount: "42660.36",
    overdue_amount: "0",
  },
};

function backend(dashboard: Dashboard) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(JSON.stringify(url === "/api/dashboard" ? dashboard : ME), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    ),
  );
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

// Testing Library junta los espacios: "$ 108.400,00" (con espacio que no corta) se busca así.
const money = (text: string) => new RegExp(`^\\$\\s${text.replace(/\./g, "\\.")}$`);

describe("Dashboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra los números del backend tal cual, sin recalcularlos", async () => {
    backend(DATA);
    renderPage();

    expect(await screen.findByText(money("108.400,00"))).toBeInTheDocument(); // deuda en gestión
    expect(screen.getByText(money("63.990,54"))).toBeInTheDocument(); // acuerdos
    // Total de la cartera: en el indicador y en el pie de la tabla por estado.
    expect(screen.getAllByText(money("167.650,50"))).toHaveLength(2);

    const table = screen.getByRole("table", { name: "Casos y deuda por estado" });
    const pending = within(table).getByRole("row", { name: /Pendiente/ });
    expect(pending).toHaveTextContent("2");
    expect(pending).toHaveTextContent(/51\.500,00/);

    // Seguimiento de pagos: lo cobrado de los acuerdos.
    const payments = screen.getByRole("table", { name: "Acuerdos por estado de pago" });
    expect(within(payments).getByRole("row", { name: /Al día/ })).toHaveTextContent("1 acuerdo");
    expect(screen.getByText(/Cobrado \$\s21\.330,18 · falta cobrar \$\s42\.660,36/)).toBeInTheDocument();
  });

  it("las pestañas Casos y Contactabilidad muestran sus números", async () => {
    backend(DATA);
    renderPage();

    await userEvent.click(await screen.findByRole("tab", { name: "Casos" }));
    const byStatus = screen.getByRole("table", { name: "Casos por estado" });
    expect(within(byStatus).getByRole("row", { name: /Pendiente/ })).toHaveTextContent("2 casos");

    await userEvent.click(screen.getByRole("tab", { name: "Contactabilidad" }));
    // 1 acuerdo sobre 3 llamadas terminadas.
    expect(screen.getByText(/^33\s%$/)).toBeInTheDocument();
    const results = screen.getByRole("table", { name: "Llamadas por resultado" });
    expect(within(results).getByRole("row", { name: /Cortó antes/ })).toHaveTextContent("1 llamada");
  });

  it("una empresa sin datos ve cómo empezar, no un tablero en cero", async () => {
    backend({
      ...DATA,
      portfolio: {
        ...DATA.portfolio,
        cases_total: 0,
        unassigned_overdue_invoices: 0,
        upcoming_invoices: 0,
      },
    });
    renderPage();

    expect(await screen.findByText("Todavía no hay datos para mostrar")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "cargar las facturas" })).toHaveAttribute(
      "href",
      "/invoices/upload",
    );
  });
});
