/**
 * Formato para mostrar montos y fechas como se leen en Argentina.
 *
 * MONTOS: el backend los manda como TEXTO exacto ("56900.50"). Acá se arman los
 * separadores a mano, sin convertir a número: así nunca se pierde un centavo.
 *
 *     "56900.50"  ->  "$ 56.900,50"
 *
 * FECHAS SIN HORA ("2026-09-10"): tampoco se usa `new Date(...)`. JavaScript la
 * interpreta como medianoche en UTC y, mostrada en Argentina (UTC-3), queda en
 * el día ANTERIOR: el 10/09 aparecería como 09/09.
 */

const BUSINESS_TIMEZONE = "America/Argentina/Buenos_Aires";

const NBSP = "\u00a0";

export function formatMoney(amount: string, currency = "ARS"): string {
  const [rawInteger = "0", rawDecimals = ""] = amount.trim().split(".");
  const negative = rawInteger.startsWith("-");
  const integer = negative ? rawInteger.slice(1) : rawInteger;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimals = rawDecimals.padEnd(2, "0");
  const symbol = currency === "ARS" ? "$" : currency;
  // Espacio que no corta: "$" y el número nunca quedan en renglones distintos.
  return `${negative ? "-" : ""}${symbol}${NBSP}${grouped},${decimals}`;
}

/** Porcentajes del backend ("10.00") -> "10 %", ("12.50") -> "12,5 %". */
export function formatPercent(value: string): string {
  const [integer = "0", decimals = ""] = value.split(".");
  const trimmed = decimals.replace(/0+$/, "");
  return `${integer}${trimmed ? `,${trimmed}` : ""}${NBSP}%`;
}

/** "2026-09-10" -> "10/09/2026" (sin pasar por Date: ver arriba). */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

/** El día, en hora argentina, de un instante: "2026-10-22T02:30:00Z" -> "2026-10-21". */
export function businessDay(isoDateTime: string): string {
  // en-CA escribe las fechas como AAAA-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone: BUSINESS_TIMEZONE }).format(new Date(isoDateTime));
}

/** Fecha y hora de un instante (ej. "2026-10-19T16:49:25Z"), en hora argentina. */
export function formatDateTime(isoDateTime: string): string {
  return new Intl.DateTimeFormat("es-AR", {
    timeZone: BUSINESS_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23", // 13:49 y no "01:49 p. m."
  }).format(new Date(isoDateTime));
}

export function formatDays(days: number): string {
  return days === 1 ? "1 día" : `${days} días`;
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes ? `${minutes} min ${rest} s` : `${rest} s`;
}

/** count(1, "factura", "facturas") -> "1 factura"; count(3, ...) -> "3 facturas". */
export function count(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

/** Como formatMoney, pero sin ",00" cuando no hay centavos: "$ 500.000". Para resúmenes. */
export function formatMoneyShort(amount: string, currency = "ARS"): string {
  return formatMoney(amount, currency).replace(/,00$/, "");
}
