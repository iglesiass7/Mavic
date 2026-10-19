import { describe, expect, it } from "vitest";

import { share } from "./dashboard";

describe("share (solo para el largo de las barras)", () => {
  it("es la parte del total, entre 0 y 1", () => {
    expect(share("51500.00", "167650.50")).toBeCloseTo(0.307, 3);
    expect(share("0.00", "100.00")).toBe(0);
    expect(share("100.00", "100.00")).toBe(1);
  });

  it("con total 0 no divide por cero", () => {
    expect(share("0.00", "0.00")).toBe(0);
  });
});
