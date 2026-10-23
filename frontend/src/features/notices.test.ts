import { describe, expect, it } from "vitest";

import { renderSample, unknownPlaceholders } from "./notices";

describe("marcadores de los avisos", () => {
  it("reemplaza los conocidos y deja el resto como está (igual que el backend)", () => {
    expect(renderSample("Hola {nombre}, {otro}", { nombre: "Ana" })).toBe("Hola Ana, {otro}");
  });

  it("encuentra los que no existen", () => {
    expect(unknownPlaceholders("{nombre} {nombr} {monto}", ["nombre", "monto"])).toEqual(["nombr"]);
  });
});
