import { describe, expect, it } from "vitest";

import { can, safeNextPath } from "./auth";
import type { Me } from "@/lib/types";

describe("safeNextPath (a dónde volver después del login)", () => {
  it.each(["/cases", "/cases/abc?status=pending"])("acepta rutas propias: %s", (path) => {
    expect(safeNextPath(path)).toBe(path);
  });

  it.each<[string | null, string]>([
    [null, "sin parámetro"],
    ["", "vacío"],
    ["https://otro-sitio.com", "otro sitio con protocolo"],
    ["//otro-sitio.com", "otro sitio sin protocolo"],
    ["/\\otro-sitio.com", "otro sitio con barra invertida"],
    ["/login", "el mismo login (evita un bucle)"],
    ["cases", "ruta relativa"],
  ])("rechaza %s (%s) y manda al inicio", (next) => {
    expect(safeNextPath(next)).toBe("/");
  });
});

describe("can (permisos del usuario)", () => {
  const me = { permissions: ["view_portfolio"] } as unknown as Me;

  it("dice que sí solo a lo que el backend habilitó", () => {
    expect(can(me, "view_portfolio")).toBe(true);
    expect(can(me, "manage_users")).toBe(false);
  });
});
