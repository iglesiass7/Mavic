/** El editor de reglas con el backend simulado. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RuleEditor } from "./RuleEditor";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RuleEditor />
    </QueryClientProvider>,
  );
}

function backend(status: number, body: unknown) {
  // Tipado con (url, init) para poder leer después qué se mandó.
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function fillValidRule() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Nombre"), "Mora media");
  // Hay tres "Hasta" (deuda, días, facturas): el primero es el de la deuda.
  const [maxAmount] = screen.getAllByLabelText("Hasta");
  await user.type(maxAmount!, "500.000");
  const discount = screen.getByLabelText("Descuento por pago único");
  await user.clear(discount);
  await user.type(discount, "12,5");
  const installments = screen.getByLabelText("Cuotas");
  await user.clear(installments);
  await user.type(installments, "3");
  return user;
}

describe("RuleEditor", () => {
  beforeEach(() => push.mockReset());
  afterEach(() => vi.unstubAllGlobals());

  it("manda la regla con los números como los entiende el backend y vuelve a la lista", async () => {
    const fetchMock = backend(201, {});
    renderEditor();
    const user = await fillValidRule();

    // La vista previa ya la cuenta en palabras antes de guardar.
    expect(screen.getByText(/12,5\s%\sde descuento/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Crear regla" }));

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/rules"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/negotiation-rules");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      name: "Mora media",
      max_amount: "500000",
      discount_pct: "12.5",
      max_installments: 3,
    });
  });

  it("si se pisa con otra regla activa, muestra el aviso del backend y no sale de la pantalla", async () => {
    backend(409, {
      detail: "Se pisa con la regla activa 'Deuda reciente sin descuento': habría casos con dos ofertas posibles.",
      code: "RULE_OVERLAP",
    });
    renderEditor();
    const user = await fillValidRule();
    await user.click(screen.getByRole("button", { name: "Crear regla" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Se pisa con la regla activa");
    expect(push).not.toHaveBeenCalled();
  });

  it("con errores en el formulario no llama al backend", async () => {
    const fetchMock = backend(201, {});
    renderEditor();
    await userEvent.click(screen.getByRole("button", { name: "Crear regla" }));

    expect(screen.getByText("La regla necesita un nombre.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
