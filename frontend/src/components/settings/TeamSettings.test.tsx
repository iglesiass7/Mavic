/** Configuración > Organización con el backend simulado (respuestas como las de GET /users). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeamSettings } from "./TeamSettings";
import type { User } from "@/lib/types";

const ME = {
  user: {
    id: "laura",
    name: "Laura Gómez",
    email: "laura@fibrasur.com",
    role: "admin",
  },
  company: { id: "c1", name: "FibraSur" },
  permissions: ["view_portfolio", "manage_users"],
};

const base = {
  company_id: "c1",
  last_login_at: null,
  created_at: "2026-10-23T00:44:29Z",
};
const USERS: User[] = [
  {
    ...base,
    id: "laura",
    name: "Laura Gómez",
    email: "laura@fibrasur.com",
    role: "admin",
    is_active: true,
  },
  {
    ...base,
    id: "martin",
    name: "Martín Ruiz",
    email: "martin@fibrasur.com",
    role: "supervisor",
    is_active: true,
  },
  {
    ...base,
    id: "pablo",
    name: "Pablo Díaz",
    email: "pablo@fibrasur.com",
    role: "operator",
    is_active: false,
  },
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function backend() {
  const sent: { method: string; url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      sent.push({ method, url, body });
      if (url === "/api/users" && method === "GET") return Promise.resolve(json(USERS));
      if (url === "/api/users" && method === "POST") {
        return Promise.resolve(json({ ...base, id: "nuevo", is_active: true, ...body }, 201));
      }
      if (url.startsWith("/api/users/")) return Promise.resolve(json({ ...USERS[1], ...body }));
      return Promise.resolve(json(ME));
    }),
  );
  return sent;
}

function renderTeam() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <TeamSettings />
    </QueryClientProvider>,
  );
}

describe("Configuración > Organización", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("primero los activos; nadie puede desactivarse ni cambiarse el rol a sí mismo", async () => {
    backend();
    renderTeam();

    const table = await screen.findByRole("table", {
      name: "Usuarios de la empresa",
    });
    await within(table).findByText("Martín Ruiz");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual([
      "Laura Gómez(vos)",
      "Martín Ruiz",
      "Pablo Díaz",
    ]);
    expect(within(rows[0]!).queryByRole("switch")).not.toBeInTheDocument();
    expect(within(rows[0]!).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(rows[2]!).getByRole("switch", { name: "Reactivar a Pablo Díaz" })).not.toBeChecked();
  });

  it("el interruptor y el rol mandan el cambio al backend", async () => {
    const sent = backend();
    renderTeam();

    await userEvent.click(await screen.findByRole("switch", { name: "Desactivar a Martín Ruiz" }));
    await userEvent.selectOptions(screen.getByLabelText("Rol de Martín Ruiz"), "admin");

    const patches = sent.filter((r) => r.method === "PATCH");
    expect(patches).toEqual([
      { method: "PATCH", url: "/api/users/martin", body: { is_active: false } },
      { method: "PATCH", url: "/api/users/martin", body: { role: "admin" } },
    ]);
  });

  it("invitar miembro: crea el usuario y muestra la contraseña una sola vez", async () => {
    const sent = backend();
    renderTeam();

    await userEvent.click(await screen.findByRole("button", { name: /Invitar miembro/ }));
    const dialog = screen.getByRole("dialog", { name: "Invitar miembro" });
    await userEvent.type(within(dialog).getByLabelText("Nombre"), "Sofía Paz");
    await userEvent.type(within(dialog).getByLabelText("Email"), "sofia@fibrasur.com");
    const password = (within(dialog).getByLabelText("Contraseña inicial") as HTMLInputElement).value;
    await userEvent.click(within(dialog).getByRole("button", { name: "Crear usuario" }));

    expect(await within(dialog).findByText("Usuario creado")).toBeInTheDocument();
    expect(within(dialog).getByText(password)).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({
      name: "Sofía Paz",
      email: "sofia@fibrasur.com",
      password,
      role: "operator",
    });
  });

  it("el buscador filtra por nombre o email", async () => {
    backend();
    renderTeam();

    await screen.findByText("Martín Ruiz");
    await userEvent.type(screen.getByPlaceholderText("Buscar por nombre o email..."), "PABLO@");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("Pablo Díaz");
  });
});
