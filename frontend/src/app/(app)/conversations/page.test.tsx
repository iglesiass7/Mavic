/** La pantalla Conversaciones con respuestas copiadas de GET /conversations (datos demo). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ConversationsPage from "./page";
import type { CallListItem, Page } from "@/lib/types";

const push = vi.fn();
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/conversations",
  useSearchParams: () => search,
}));

const ME = {
  user: { id: "u1", name: "Laura Gómez", role: "admin" },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "operate_portfolio"],
};

const CONTACTED: CallListItem = {
  call: {
    id: "8a4db638-cfdd-41a7-a3d3-d21ddec9f0e3",
    provider_conversation_id: "conv_demo_16",
    origin: "EXTERNAL",
    status: "DONE",
    failure_reason: null,
    review_reason: null,
    started_at: "2026-10-23T00:44:52.236534Z",
    identity_verified: null,
    offered: [],
    result: "CONTACTADO",
    unknown_count: null,
    agreement: null,
    summary: "Atendió y escuchó las opciones.",
    call_duration_secs: 87,
    transcript: [
      { role: "agent", message: "Hola, ¿hablo con Lucía Fernández?", time_in_call_secs: 0 },
      { role: "user", message: "Sí, soy yo.", time_in_call_secs: 3 },
    ],
  },
  case_id: "92aac44e-bdf2-4c9b-9ddc-3ec696448749",
  case_number: 16,
  case_status: "contacted",
  debtor_name: "Lucía Fernández",
};

const ESCALATED: CallListItem = {
  ...CONTACTED,
  call: {
    ...CONTACTED.call,
    id: "5f0c1d2e-0000-4000-8000-000000000011",
    result: "DERIVACION_HUMANA",
    summary: "Pidió hablar con una persona.",
    transcript: [{ role: "user", message: "Quiero hablar con alguien.", time_in_call_secs: 4 }],
  },
  case_id: "11111111-2222-4333-8444-555555555555",
  case_number: 11,
  case_status: "escalated",
  debtor_name: "Florencia Acosta",
};

function backend(items: CallListItem[]) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      const body: Page<CallListItem> | typeof ME = url.startsWith("/api/conversations")
        ? { items, total: items.length, limit: 30, offset: 0 }
        : ME;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }),
      );
    }),
  );
  return urls;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConversationsPage />
    </QueryClientProvider>,
  );
}

describe("Conversaciones", () => {
  beforeEach(() => {
    search = new URLSearchParams();
    push.mockReset();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lista las llamadas y muestra la primera, con su transcripción", async () => {
    backend([CONTACTED, ESCALATED]);
    renderPage();

    const list = await screen.findByRole("region", { name: "Llamadas" });
    expect(await within(list).findByRole("button", { name: /Caso #16.*Contactado/ })).toHaveAttribute("aria-current", "true");
    expect(within(list).getByRole("button", { name: /Caso #11.*Derivada/ })).toBeInTheDocument();

    const chat = screen.getByRole("region", { name: "Conversación" });
    expect(within(chat).getByText("Atendió y escuchó las opciones.")).toBeInTheDocument();
    const turns = within(chat).getByRole("list", { name: "Transcripción" });
    expect(within(turns).getAllByRole("listitem")).toHaveLength(2);
    expect(await within(chat).findByRole("button", { name: /Derivar a humano/ })).toBeInTheDocument();
  });

  it("elegir otra llamada la pone en la dirección", async () => {
    backend([CONTACTED, ESCALATED]);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /Caso #11/ }));
    expect(push).toHaveBeenCalledWith(`/conversations?llamada=${ESCALATED.call.id}`, { scroll: false });
  });

  it("un caso que ya no se negocia no ofrece derivarlo de nuevo", async () => {
    search = new URLSearchParams(`llamada=${ESCALATED.call.id}`);
    const urls = backend([CONTACTED, ESCALATED]);
    renderPage();

    const chat = await screen.findByRole("region", { name: "Conversación" });
    expect(await within(chat).findByText("Quiero hablar con alguien.")).toBeInTheDocument();
    // Esperar a que lleguen los permisos: sin esto el botón falta por otra razón.
    await waitFor(() => expect(urls).toContain("/api/auth/me"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(chat).queryByRole("button", { name: /Derivar a humano/ })).not.toBeInTheDocument();
  });

  it("los filtros viajan al backend y a la dirección", async () => {
    search = new URLSearchParams("q=%2316&estado=contactado");
    const urls = backend([CONTACTED]);
    renderPage();

    await screen.findByRole("button", { name: /Caso #16/ });
    expect(urls.find((url) => url.startsWith("/api/conversations"))).toContain("q=%2316");
    expect(urls.find((url) => url.startsWith("/api/conversations"))).toContain("outcome=CONTACTADO");

    await userEvent.selectOptions(screen.getByLabelText("Estado"), "ACUERDO");
    expect(push).toHaveBeenCalledWith("/conversations?q=%2316&estado=acuerdo", { scroll: false });
  });

  it("sin llamadas, explica qué va a aparecer", async () => {
    backend([]);
    renderPage();
    expect(await screen.findByText(/Todavía no hubo llamadas/)).toBeInTheDocument();
  });
});
