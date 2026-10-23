/** Seguimiento de pagos en el detalle del caso, con una respuesta como la de GET /cases/{id}/agreements. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgreementsSection } from "./AgreementsSection";
import type { AgreementTracking } from "@/lib/types";

const ME = {
  user: { id: "u1", name: "Pablo Díaz", role: "operator" },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "operate_portfolio"],
};

const AGREEMENT: AgreementTracking = {
  id: "a1",
  case_id: "case-1",
  conversation_id: "conv-1",
  offer_id: "CUOTAS-3-CON-INTERES",
  modality: "CUOTAS",
  currency: "ARS",
  original_amount: "30000.00",
  total_amount: "33000.00",
  installment_count: 3,
  installment_amount: "11000.00",
  discount_pct: null,
  discount_amount: null,
  created_at: "2026-10-20T15:00:00Z",
  status: "late",
  paid_amount: "11000.00",
  pending_amount: "22000.00",
  next_due_date: "2026-11-25",
  installments: [
    {
      number: 1,
      due_date: "2026-10-25",
      amount: "11000.00",
      paid_on: "2026-10-22",
      paid_recorded_at: "2026-10-23T10:00:00Z",
      note: "transferencia",
      overdue: false,
    },
    {
      number: 2,
      due_date: "2026-11-25",
      amount: "11000.00",
      paid_on: null,
      paid_recorded_at: null,
      note: null,
      overdue: true,
    },
    {
      number: 3,
      due_date: "2026-12-25",
      amount: "11000.00",
      paid_on: null,
      paid_recorded_at: null,
      note: null,
      overdue: false,
    },
  ],
};

function backend() {
  const sent: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      sent.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const body = url.startsWith("/api/auth/me")
        ? ME
        : url.endsWith("/agreements")
          ? [AGREEMENT]
          : AGREEMENT;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }),
      );
    }),
  );
  return sent;
}

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AgreementsSection caseId="case-1" />
    </QueryClientProvider>,
  );
}

describe("AgreementsSection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra el estado, lo cobrado y cada cuota", async () => {
    backend();
    renderSection();

    expect(await screen.findByText("Atrasado")).toBeInTheDocument();
    const installments = screen.getByRole("list", { name: "Cuotas" });
    const rows = within(installments).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Pagada el 22/10/2026");
    expect(rows[1]).toHaveTextContent("Vencida sin pagar");
    expect(rows[2]).toHaveTextContent("Pendiente");
    expect(screen.getByRole("progressbar", { name: "Cobrado del acuerdo" })).toHaveAttribute(
      "aria-valuenow",
      "33",
    );
  });

  it("registrar un pago manda el día y la nota", async () => {
    const sent = backend();
    renderSection();

    const installments = await screen.findByRole("list", { name: "Cuotas" });
    const second = within(installments).getAllByRole("listitem")[1]!;
    await userEvent.click(await within(second).findByRole("button", { name: "Registrar pago" }));
    const date = within(second).getByLabelText("Día en que pagó");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-10-22");
    await userEvent.type(within(second).getByLabelText("Nota (opcional)"), "efectivo");
    await userEvent.click(within(second).getByRole("button", { name: /Registrar pago de/ }));

    await vi.waitFor(() =>
      expect(sent.find((r) => r.url === "/api/agreements/a1/installments/2/payment")?.body).toEqual({
        paid_on: "2026-10-22",
        note: "efectivo",
      }),
    );
  });

  it("anular un pago pide el motivo", async () => {
    const sent = backend();
    renderSection();

    const installments = await screen.findByRole("list", { name: "Cuotas" });
    const first = within(installments).getAllByRole("listitem")[0]!;
    await userEvent.click(await within(first).findByRole("button", { name: "Anular" }));
    const confirm = within(first).getByRole("button", { name: "Anular el pago" });
    expect(confirm).toBeDisabled();

    await userEvent.type(within(first).getByLabelText(/Por qué se anula/), "Se cargó por error");
    await userEvent.click(confirm);

    await vi.waitFor(() =>
      expect(sent.find((r) => r.url.endsWith("/installments/1/undo-payment"))?.body).toEqual({
        reason: "Se cargó por error",
      }),
    );
  });
});
