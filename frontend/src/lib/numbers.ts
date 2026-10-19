/**
 * Números que escribe la persona en un formulario.
 *
 * En Argentina se escribe "500.000" (punto de miles) y "12,5" (coma decimal),
 * pero también hay quien escribe "500000" o "12.5". Estas funciones entienden
 * las dos formas y devuelven TEXTO con punto decimal ("500000", "12.5"), que es
 * lo que acepta el backend. Igual que con los montos (ADR-028): nada pasa por
 * `Number`, así no se pierden centavos.
 */

/**
 * "500.000" -> "500000"; "1.234,5" -> "1234.5"; "12,5" -> "12.5"; "12.5" -> "12.5".
 * Devuelve null si no es un número válido o si tiene más de `decimals` decimales.
 */
export function parseDecimalInput(text: string, decimals = 2): string | null {
  let value = text.trim().replace(/\s/g, "").replace(/^\$/, "");
  if (value === "") return null;

  if (value.includes(",")) {
    // Hay coma: es la coma decimal y los puntos son de miles.
    if (!/^\d{1,3}(\.\d{3})*(,\d+)?$|^\d+(,\d+)?$/.test(value)) return null;
    value = value.replace(/\./g, "").replace(",", ".");
  } else if (/^\d{1,3}(\.\d{3})+$/.test(value)) {
    // "500.000" o "1.250.000": puntos de miles, sin decimales.
    value = value.replace(/\./g, "");
  } else if (!/^\d+(\.\d+)?$/.test(value)) {
    return null;
  }

  const [integer = "0", fraction = ""] = value.split(".");
  if (fraction.length > decimals) return null;
  const cleanInteger = integer.replace(/^0+(?=\d)/, "");
  return fraction ? `${cleanInteger}.${fraction}` : cleanInteger;
}

/** Enteros sin signo: "15" -> 15. Los días y las cantidades nunca son enormes. */
export function parseIntegerInput(text: string): number | null {
  const value = text.trim().replace(/\./g, "");
  if (!/^\d{1,6}$/.test(value)) return null;
  return Number(value);
}

/**
 * El valor del backend como se lo mostraría a una persona en el formulario:
 * "500000.00" -> "500.000"; "500000.01" -> "500.000,01"; "12.50" -> "12,5".
 */
export function decimalToInput(value: string): string {
  const [integer = "0", fraction = ""] = value.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const trimmed = fraction.replace(/0+$/, "");
  return trimmed ? `${grouped},${trimmed}` : grouped;
}

/** Compara dos números en texto ("500000" y "1500.5") sin pasarlos por `Number`. */
export function compareDecimals(a: string, b: string): number {
  const [ai = "0", af = ""] = a.split(".");
  const [bi = "0", bf = ""] = b.split(".");
  if (ai.length !== bi.length) return ai.length < bi.length ? -1 : 1;
  if (ai !== bi) return ai < bi ? -1 : 1;
  const width = Math.max(af.length, bf.length);
  const fa = af.padEnd(width, "0");
  const fb = bf.padEnd(width, "0");
  return fa === fb ? 0 : fa < fb ? -1 : 1;
}
