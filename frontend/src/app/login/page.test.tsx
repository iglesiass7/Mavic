import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

const replace = vi.fn();
let nextParam: string | null = null;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(nextParam ? { next: nextParam } : {}),
}));

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LoginPage />
    </QueryClientProvider>,
  );
}

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
}

describe("pantalla de login", () => {
  beforeEach(() => {
    replace.mockReset();
    nextParam = null;
  });
  afterEach(() => vi.unstubAllGlobals());

  it("con datos incorrectos muestra el mensaje del backend y no navega", async () => {
    respond(401, { detail: "Email o contraseña incorrectos.", code: "INVALID_CREDENTIALS" });
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "laura@fibrasur.com");
    await userEvent.type(screen.getByLabelText("Contraseña"), "mal");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email o contraseña incorrectos.");
    expect(replace).not.toHaveBeenCalled();
  });

  it("con datos correctos vuelve a la pantalla que se quería abrir", async () => {
    nextParam = "/cases?status=pending";
    respond(200, { user: { name: "Laura" }, company: null, permissions: [] });
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "laura@fibrasur.com");
    await userEvent.type(screen.getByLabelText("Contraseña"), "bien");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/cases?status=pending"));
  });

  it("el botón no se puede usar con campos vacíos", () => {
    renderLogin();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeDisabled();
  });
});
