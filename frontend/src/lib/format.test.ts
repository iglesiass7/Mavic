import {
  businessDay,
  count,
  formatDate,
  formatDateTime,
  formatDays,
  formatDuration,
  formatMoney,
  formatPercent,
} from "./format";

describe("formatMoney", () => {
  it.each([
    ["56900.00", "$\u00a056.900,00"],
    ["56900.5", "$\u00a056.900,50"],
    ["1234567.89", "$\u00a01.234.567,89"],
    ["999.99", "$\u00a0999,99"],
    ["0", "$\u00a00,00"],
    ["10621.33", "$\u00a010.621,33"],
  ])("%s -> %s", (amount, expected) => {
    expect(formatMoney(amount)).toBe(expected);
  });

  it("never loses cents, even where a float would", () => {
    // 0.1 + 0.2 en float da 0.30000000000000004; acá no hay floats.
    expect(formatMoney("999999999999.99")).toBe("$\u00a0999.999.999.999,99");
  });
});

describe("formatPercent", () => {
  it.each([
    ["10.00", "10\u00a0%"],
    ["12.50", "12,5\u00a0%"],
    ["0.00", "0\u00a0%"],
  ])("%s -> %s", (value, expected) => {
    expect(formatPercent(value)).toBe(expected);
  });
});

describe("formatDate", () => {
  it("does not shift the day because of the timezone", () => {
    // Con new Date("2026-09-10") en Argentina daría 09/09/2026.
    expect(formatDate("2026-09-10")).toBe("10/09/2026");
  });
});

describe("formatDateTime", () => {
  it("shows the Argentine local time", () => {
    // 16:49 UTC = 13:49 en Buenos Aires.
    expect(formatDateTime("2026-10-19T16:49:25Z")).toContain("13:49");
  });
});

describe("small helpers", () => {
  it("pluralizes days", () => {
    expect(formatDays(1)).toBe("1 día");
    expect(formatDays(36)).toBe("36 días");
  });

  it("formats call durations", () => {
    expect(formatDuration(42)).toBe("42 s");
    expect(formatDuration(95)).toBe("1 min 35 s");
  });
});

describe("count", () => {
  it("usa singular solo para 1", () => {
    expect(count(1, "factura", "facturas")).toBe("1 factura");
    expect(count(0, "factura", "facturas")).toBe("0 facturas");
    expect(count(8, "factura", "facturas")).toBe("8 facturas");
  });
});

describe("businessDay", () => {
  it("usa el día de Argentina, no el de UTC", () => {
    expect(businessDay("2026-10-23T00:44:52Z")).toBe("2026-10-22"); // 21:44 en Buenos Aires
    expect(businessDay("2026-10-23T03:00:00Z")).toBe("2026-10-23"); // medianoche en Buenos Aires
  });
});
