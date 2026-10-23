/** La auditoría con una respuesta como la de GET /audit-events. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AuditPage from "./page";
import type { AuditEvent, Page } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/audit",
  useSearchParams: () => new URLSearchParams(),
}));

const EVENT: AuditEvent = {
  id: "e1",
  occurred_at: "2026-10-23T09:55:00Z",
  actor_kind: "user",
  actor_name: "Laura Gómez",
  action: "RULE_UPDATED",
  level: "critical",
  subject_kind: "rule",
  subject_id: "r1",
  subject_label: "Regla 'Mora alta'",
  summary: "Cambió la regla 'Mora alta': descuento (%).",
  details: { cambios: { "Descuento (%)": { antes: "10.00", despues: "15.00" } } },
};

function backend() {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      const body: Page<AuditEvent> = { items: [EVENT], total: 1, limit: 20, offset: 0 };
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }),
      );
    }),
  );
  return urls;
}

describe("Auditoría", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lista los eventos y muestra el antes y después de un cambio", async () => {
    backend();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <AuditPage />
      </QueryClientProvider>,
    );

    const row = await screen.findByRole("row", { name: /Laura Gómez/ });
    expect(row).toHaveTextContent("Cambio de regla");
    expect(row).toHaveTextContent("Crítico");

    await userEvent.click(within(row).getByRole("button", { name: /Ver el detalle/ }));
    const dialog = screen.getByRole("dialog", { name: "Detalle del evento" });
    const change = within(dialog).getByRole("row", { name: /Descuento/ });
    expect(change).toHaveTextContent("10.00");
    expect(change).toHaveTextContent("15.00");
  });

  it("el tipo de evento va a la dirección", async () => {
    backend();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <AuditPage />
      </QueryClientProvider>,
    );
    await screen.findByRole("row", { name: /Laura Gómez/ });

    await userEvent.selectOptions(screen.getByLabelText("Tipo de evento"), "payments");

    expect(push).toHaveBeenCalledWith("/audit?tema=pagos", { scroll: false });
  });
});
