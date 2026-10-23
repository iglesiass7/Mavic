/** El botón de avisos de Facturas, con respuestas como las de /notices/preview y /notices/send. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NoticeAction } from "./NoticeAction";
import type { NoticePreview, NoticeSendReport } from "@/lib/types";

const PREVIEW: NoticePreview = {
  stage: "preventive",
  channel: "email",
  channel_ready: true,
  enabled: true,
  send_time: "09:00",
  first_due: "2026-10-24",
  last_due: "2026-11-07",
  to_send: 18,
  already_sent: 2,
  without_contact: 1,
  sample_subject: "Tu factura DEMO-3001 vence el 02/11/2026",
  sample_body: "Hola Agustina Romero: ...",
};

const REPORT: NoticeSendReport = {
  stage: "preventive",
  channel: "email",
  sent: 17,
  failed: 1,
  already_sent: 2,
  without_contact: 1,
  remaining: 0,
  errors: ["DEMO-3009: El servidor de email rechazó la dirección del deudor."],
};

function backend(preview: NoticePreview) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      const body = url.startsWith("/api/notices/send") ? REPORT : preview;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }),
      );
    }),
  );
  return calls;
}

function renderAction(canOperate = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <NoticeAction stage="preventive" canOperate={canOperate} />
    </QueryClientProvider>,
  );
}

describe("NoticeAction", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra a quién le toca y pide confirmar con el primer aviso a la vista", async () => {
    const calls = backend(PREVIEW);
    renderAction();

    expect(await screen.findByText(/vencen del 24\/10\/2026 al 07\/11\/2026/)).toBeInTheDocument();
    expect(screen.getByText(/18 por mandar · 2 ya avisadas · 1 sin email/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Enviar 18 avisos/ }));
    expect(screen.getByText("Tu factura DEMO-3001 vence el 02/11/2026")).toBeInTheDocument();
    expect(calls).not.toContain("POST /api/notices/send"); // todavía no mandó nada

    await userEvent.click(screen.getByRole("button", { name: "Confirmar envío" }));

    expect(await screen.findByText(/17 avisos mandados por Email, 1 falló/)).toBeInTheDocument();
    expect(screen.getByText(/DEMO-3009/)).toBeInTheDocument();
    expect(calls).toContain("POST /api/notices/send");
  });

  it("sin el canal configurado no ofrece mandar y dice qué falta", async () => {
    backend({ ...PREVIEW, channel: "whatsapp", channel_ready: false });
    renderAction();

    expect(await screen.findByText(/faltan TWILIO_ACCOUNT_SID/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enviar/ })).not.toBeInTheDocument();
  });

  it("el supervisor ve el estado pero no el botón", async () => {
    backend(PREVIEW);
    renderAction(false);

    expect(await screen.findByText(/18 por mandar/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enviar/ })).not.toBeInTheDocument();
  });
});
