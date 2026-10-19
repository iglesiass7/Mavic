import { describe, expect, it } from "vitest";

import { checkFile } from "./invoices";

function fileOf(name: string, bytes: number): File {
  return new File([new Uint8Array(bytes)], name);
}

describe("checkFile (revisión rápida antes de subir)", () => {
  it.each(["facturas.csv", "Facturas Octubre.XLSX"])("acepta %s", (name) => {
    expect(checkFile(fileOf(name, 100))).toBeNull();
  });

  it("rechaza otros formatos (el backend no los lee)", () => {
    expect(checkFile(fileOf("facturas.xls", 100))).toMatch(/\.csv o \.xlsx/);
    expect(checkFile(fileOf("facturas.pdf", 100))).toMatch(/\.csv o \.xlsx/);
  });

  it("rechaza archivos de más de 5 MB y vacíos", () => {
    expect(checkFile(fileOf("grande.csv", 5 * 1024 * 1024 + 1))).toMatch(/5 MB/);
    expect(checkFile(fileOf("vacio.csv", 0))).toMatch(/vacío/);
  });
});
