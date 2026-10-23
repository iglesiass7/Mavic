/** El formulario de un aviso, con el backend simulado. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NoticeSettingsForm } from "./NoticeSettingsForm";
import type { NoticeSettings } from "@/lib/types";

const DATA: NoticeSettings = {
  stages: [
    {
      stage: "preventive",
      enabled: false,
      channel: "email",
      send_time: "09:00",
      days_before: 5,
      email_subject: "Tu factura {numero_factura} vence el {vencimiento}",
      message: "Hola {nombre}: tu factura vence el {vencimiento}.",
      instructions: "",
      whatsapp_template_sid: null,
    },
  ],
  channels_ready: { email: true, whatsapp: false },
  placeholders: [
    { name: "nombre", description: "Nombre del deudor" },
    { name: "monto", description: "Monto" },
    { name: "vencimiento", description: "Vencimiento" },
    { name: "numero_factura", description: "Número" },
    { name: "instrucciones", description: "Cómo pagar" },
  ],
  template_variables: ["nombre", "numero_factura", "monto", "vencimiento", "empresa"],
};

function backend() {
  const sent: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      sent.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return Promise.resolve(
        new Response(JSON.stringify(DATA), { status: 200, headers: { "content-type": "application/json" } }),
      );
    }),
  );
  return sent;
}

function renderForm(canManage = true) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <NoticeSettingsForm settings={DATA.stages[0]!} data={DATA} canManage={canManage} />
    </QueryClientProvider>,
  );
}

describe("NoticeSettingsForm", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra cómo lo recibe el deudor mientras se escribe", async () => {
    backend();
    renderForm();

    const preview = screen.getByRole("complementary", { name: "Así lo recibe el deudor" });
    expect(within(preview).getByText("Hola Ana Torres: tu factura vence el 25/10/2026.")).toBeInTheDocument();
    expect(within(preview).getByText("Tu factura FS-1004 vence el 25/10/2026")).toBeInTheDocument();
  });

  it("un marcador mal escrito se marca y no se guarda", async () => {
    const sent = backend();
    renderForm();
    const message = screen.getByLabelText("Texto del aviso");

    await userEvent.type(message, " Debés {{monto}"); // userEvent: "{{" escribe una llave
    await userEvent.type(message, " {{nombr}");
    await userEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(screen.getByText(/No existe \{nombr\}/)).toBeInTheDocument();
    expect(sent.filter((r) => r.url.includes("notice-settings"))).toEqual([]);
  });

  it("guarda lo que se cambió", async () => {
    const sent = backend();
    renderForm();

    await userEvent.click(screen.getByRole("switch", { name: "Envío automático todos los días" }));
    const days = screen.getByLabelText("Días antes del vencimiento");
    await userEvent.clear(days);
    await userEvent.type(days, "3");
    await userEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    const put = sent.find((r) => r.url === "/api/notice-settings/preventive");
    expect(put?.body).toMatchObject({ enabled: true, days_before: 3, channel: "email" });
    expect(await screen.findByText("Cambios guardados.")).toBeInTheDocument();
  });

  it("avisa si el canal elegido no está configurado en el servidor", async () => {
    backend();
    renderForm();

    await userEvent.selectOptions(screen.getByLabelText("Canal de envío"), "whatsapp");

    expect(screen.getByText(/WhatsApp todavía no está configurado/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Asunto del email")).not.toBeInTheDocument();
  });

  it("quien no maneja las reglas lo ve sin poder cambiarlo", () => {
    backend();
    renderForm(false);

    expect(screen.queryByRole("button", { name: "Guardar cambios" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Texto del aviso")).toBeDisabled();
  });
});
