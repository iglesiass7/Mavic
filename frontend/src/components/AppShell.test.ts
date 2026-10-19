import { describe, expect, it } from "vitest";

import { activeHref } from "./AppShell";

const HREFS = ["/cases", "/invoices", "/invoices/upload"];

describe("activeHref (qué ítem del menú se marca)", () => {
  it.each([
    ["/cases", "/cases"],
    ["/cases/abc-123", "/cases"],
    ["/invoices", "/invoices"],
    ["/invoices/upload", "/invoices/upload"], // el más específico, no "Facturas"
    ["/otra-cosa", undefined],
    ["/casesx", undefined], // que empiece igual no alcanza
  ])("%s -> %s", (pathname, expected) => {
    expect(activeHref(pathname, HREFS)).toBe(expected);
  });
});
