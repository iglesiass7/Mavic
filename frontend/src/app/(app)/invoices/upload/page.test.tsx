/**
 * El flujo de carga completo, con el backend simulado: elegir archivo,
 * revisar y cargar. Las respuestas imitan las reales de /imports/preview e /imports.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UploadPage from "./page";
import type { ImportReport } from "@/lib/types";

const ME = {
  user: { id: "u1", name: "Pablo Díaz", role: "operator" },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "operate_portfolio"],
};

const OK_REPORT: ImportReport = {
  ok: true,
  total_rows: 10,
  debtors_created: 5,
  debtors_updated: 0,
  invoices_created: 10,
  invoices_updated: 0,
  invoices_unchanged: 0,
  errors: [],
  import_id: null,
};

const BAD_REPORT: ImportReport = {
  ...OK_REPORT,
  ok: false,
  total_rows: 4,
  invoices_created: 0,
  debtors_created: 0,
  errors: [
    { row: 3, column: "amount", code: "INVALID_AMOUNT", message: "El monto 'dieciocho mil' no es un número." },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** Backend simulado: responde según la dirección y anota qué se pidió. */
function fakeBackend(preview: ImportReport) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const path = url.split("?")[0] ?? url;
      calls.push(`${init?.method ?? "GET"} ${path}`);
      if (path === "/api/auth/me") return Promise.resolve(json(ME));
      if (path === "/api/imports" && init?.method === "POST") {
        return Promise.resolve(json({ ...preview, import_id: "imp-1" }, 201));
      }
      if (path === "/api/imports") return Promise.resolve(json([]));
      if (path === "/api/imports/preview") return Promise.resolve(json(preview));
      if (path === "/api/invoices") return Promise.resolve(json({ items: [], total: 8, limit: 1, offset: 0 }));
      return Promise.resolve(json({ detail: "no simulado" }, 500));
    }),
  );
  return calls;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UploadPage />
    </QueryClientProvider>,
  );
}

const csv = (name = "facturas.csv") => new File(["external_id;description\n"], name);

describe("Cargar facturas", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("revisa, muestra qué se va a guardar y carga solo cuando se confirma", async () => {
    const calls = fakeBackend(OK_REPORT);
    renderPage();

    await userEvent.upload(await screen.findByLabelText("Archivo de facturas"), csv());

    expect(await screen.findByText(/Está todo bien: 10 filas sin problemas/)).toBeInTheDocument();
    expect(calls).toContain("POST /api/imports/preview");
    expect(calls).not.toContain("POST /api/imports"); // revisar no guarda

    await userEvent.click(screen.getByRole("button", { name: "Cargar 10 facturas" }));

    expect(await screen.findByText("Se cargó facturas.csv")).toBeInTheDocument();
    expect(calls).toContain("POST /api/imports");
    // Y ofrece el paso siguiente: agrupar las vencidas en casos.
    expect(await screen.findByRole("button", { name: "Generar casos" })).toBeInTheDocument();
  });

  it("si el archivo tiene errores, los muestra por fila y no deja cargar", async () => {
    fakeBackend(BAD_REPORT);
    renderPage();

    await userEvent.upload(await screen.findByLabelText("Archivo de facturas"), csv());

    const table = await screen.findByRole("table");
    expect(within(table).getByText("El monto 'dieciocho mil' no es un número.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Cargar/ })).not.toBeInTheDocument();
  });

  it("un archivo que no es .csv ni .xlsx ni se manda al backend", async () => {
    const calls = fakeBackend(OK_REPORT);
    renderPage();

    // applyAccept: false simula a alguien que elige "Todos los archivos" en la ventana.
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(await screen.findByLabelText("Archivo de facturas"), csv("notas.txt"));

    expect(await screen.findByRole("alert")).toHaveTextContent(".csv o .xlsx");
    expect(calls).not.toContain("POST /api/imports/preview");
  });
});
