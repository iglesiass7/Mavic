import { describe, expect, it } from "vitest";

import { compareDecimals, decimalToInput, parseDecimalInput, parseIntegerInput } from "./numbers";

describe("parseDecimalInput (lo que escribe la persona -> texto para el backend)", () => {
  it.each([
    ["500.000", "500000"], // punto de miles, como se escribe en Argentina
    ["1.250.000", "1250000"],
    ["1.250,50", "1250.50"],
    ["12,5", "12.5"],
    ["12.5", "12.5"], // también con punto decimal
    ["500000", "500000"],
    ["$ 500.000", "500000"],
    ["0", "0"],
    ["007", "7"],
  ])("%s -> %s", (input, expected) => {
    expect(parseDecimalInput(input)).toBe(expected);
  });

  it.each(["", "abc", "12,5,3", "1.2.3", "-5", "12,345"])("rechaza %j", (input) => {
    // "12,345" tiene 3 decimales: los montos y porcentajes tienen 2 como máximo.
    expect(parseDecimalInput(input)).toBeNull();
  });
});

describe("parseIntegerInput", () => {
  it("lee enteros y rechaza el resto", () => {
    expect(parseIntegerInput("15")).toBe(15);
    expect(parseIntegerInput(" 90 ")).toBe(90);
    expect(parseIntegerInput("1.000")).toBe(1000);
    expect(parseIntegerInput("2,5")).toBeNull();
    expect(parseIntegerInput("-3")).toBeNull();
    expect(parseIntegerInput("")).toBeNull();
  });
});

describe("decimalToInput (valor del backend -> como se muestra en el campo)", () => {
  it.each([
    ["500000.00", "500.000"],
    ["500000.01", "500.000,01"],
    ["12.50", "12,5"],
    ["0.00", "0"],
  ])("%s -> %s", (input, expected) => {
    expect(decimalToInput(input)).toBe(expected);
  });

  it("ida y vuelta: lo que se muestra se vuelve a leer igual", () => {
    for (const value of ["500000", "1250.5", "0", "99.99"]) {
      expect(parseDecimalInput(decimalToInput(value))).toBe(value);
    }
  });
});

describe("compareDecimals (sin pasar por Number)", () => {
  it.each([
    ["10", "9", 1],
    ["9", "10", -1],
    ["500000", "500000.00", 0],
    ["500000.01", "500000", 1],
    ["99.99", "100", -1],
  ] as const)("%s vs %s -> %i", (a, b, expected) => {
    expect(compareDecimals(a, b)).toBe(expected);
  });
});
