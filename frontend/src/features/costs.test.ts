import { describe, expect, it } from "vitest";

import { currentMonth, monthName, shiftMonth } from "./costs";

describe("meses del medidor", () => {
  it("se mueve de año sin problemas", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
  });

  it("el mes actual es el de Argentina, no el de UTC", () => {
    // 1/11 a las 01:00 UTC todavía es 31/10 en Buenos Aires.
    expect(currentMonth(new Date("2026-11-01T01:00:00Z"))).toBe("2026-10");
  });

  it("nombre del mes en castellano", () => {
    expect(monthName("2026-10")).toBe("octubre de 2026");
  });
});
