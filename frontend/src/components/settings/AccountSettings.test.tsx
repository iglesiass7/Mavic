/** Cambiar la contraseña, con el backend simulado. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountSettings } from "./AccountSettings";

const ME = {
  user: {
    id: "u1",
    name: "Laura Gómez",
    email: "laura@fibrasur.com",
    role: "admin",
  },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "manage_users"],
};

function json(body: unknown, status = 200) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function backend(passwordResponse: () => Response) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/auth/password") return Promise.resolve(passwordResponse());
      return Promise.resolve(json(ME));
    }),
  );
  return calls;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AccountSettings />
    </QueryClientProvider>,
  );
}

async function fill(current: string, next: string, repeat: string) {
  const user = userEvent.setup();
  if (current) await user.type(screen.getByLabelText("Contraseña actual"), current);
  if (next) await user.type(screen.getByLabelText("Contraseña nueva"), next);
  if (repeat) await user.type(screen.getByLabelText("Repetí la contraseña nueva"), repeat);
  await user.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
}

describe("Mi cuenta: cambiar contraseña", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("si la repetición no coincide, avisa y no manda nada", async () => {
    const calls = backend(() => json(null, 204));
    renderPage();
    await screen.findByDisplayValue("Laura Gómez");
    await fill("demo-mavic-2026", "una frase larga", "otra frase larga");

    expect(screen.getByText("No coincide con la nueva.")).toBeInTheDocument();
    expect(calls).not.toContain("PUT /api/auth/password");
  });

  it("si la actual es incorrecta, lo dice y NO saca al usuario de la app", async () => {
    backend(() =>
      json(
        {
          detail: "La contraseña actual es incorrecta.",
          code: "INVALID_CURRENT_PASSWORD",
        },
        422,
      ),
    );
    renderPage();
    await screen.findByDisplayValue("Laura Gómez");
    await fill("mal-mal-mal", "una frase larga", "una frase larga");

    expect(await screen.findByRole("alert")).toHaveTextContent("La contraseña actual es incorrecta.");
  });

  it("si sale bien, avisa que se cerraron las otras sesiones y limpia los campos", async () => {
    const calls = backend(() => new Response(null, { status: 204 }));
    renderPage();
    await screen.findByDisplayValue("Laura Gómez");
    await fill("demo-mavic-2026", "una frase larga", "una frase larga");

    expect(await screen.findByText(/Listo, cambiaste tu contraseña/)).toBeInTheDocument();
    expect(calls).toContain("PUT /api/auth/password");
    expect(screen.getByLabelText("Contraseña actual")).toHaveValue("");
  });
});
