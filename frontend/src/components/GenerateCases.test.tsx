import { describe, expect, it } from "vitest";

import { generationSummary } from "./GenerateCases";

describe("generationSummary (el resultado de generar casos, en palabras)", () => {
  it("solo casos nuevos", () => {
    expect(generationSummary({ cases_created: 4, cases_updated: 0, invoices_assigned: 8 })).toBe(
      "Se agruparon 8 facturas en 4 casos nuevos.",
    );
  });

  it("facturas que se suman a un caso pendiente que ya existía", () => {
    expect(generationSummary({ cases_created: 0, cases_updated: 1, invoices_assigned: 1 })).toBe(
      "Se agrupó 1 factura en 1 caso pendiente que ya existía.",
    );
  });

  it("las dos cosas a la vez", () => {
    expect(generationSummary({ cases_created: 1, cases_updated: 2, invoices_assigned: 5 })).toBe(
      "Se agruparon 5 facturas en 1 caso nuevo y 2 casos pendientes que ya existían.",
    );
  });

  it("no había nada para agrupar", () => {
    expect(generationSummary({ cases_created: 0, cases_updated: 0, invoices_assigned: 0 })).toBe(
      "No había facturas vencidas sin caso: no se cambió nada.",
    );
  });
});
