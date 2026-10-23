"use client";

/**
 * Piezas de gráfico con el diseño de Rynx (las usan el tablero y el medidor de costos).
 *
 * Guía de visualización:
 *   - cantidades por categoría -> barras de UN color (es magnitud, no identidad)
 *   - cada barra tiene su valor escrito, y al pasar el mouse o con el teclado, el detalle
 *   - todo gráfico tiene la misma información como tabla, para lectores de pantalla
 */
import type { ReactNode } from "react";

import { Card, cx } from "./ui";

/** Una tarjeta de gráfico de Rynx: título a la izquierda, contenido abajo. */
export function ChartCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <Card className="p-6">
      <h2 className="mb-5 text-[15px] font-bold text-ink">{title}</h2>
      {children}
      {footer && <p className="mt-4 text-xs text-muted">{footer}</p>}
    </Card>
  );
}

/**
 * Detalle al pasar el mouse (o al llegar con el teclado). El valor principal
 * ya está escrito al lado de la barra: esto agrega el resto (monto, porcentaje).
 */
export function Tip({
  text,
  children,
  className,
}: {
  text: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div tabIndex={0} aria-label={text} className={cx("group relative outline-none", className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute -top-9 left-1/2 z-20 hidden -translate-x-1/2 rounded-lg bg-rynx-dark px-2.5 py-1.5 text-xs whitespace-nowrap text-white shadow-lg group-hover:block group-focus:block"
      >
        {text}
      </span>
    </div>
  );
}

export interface BarRow {
  key: string;
  label: string;
  value: number;
  valueText: string;
  tip: string;
  fill?: string; // clase de color; por defecto el verde de la marca
}

/** Barras horizontales: nombre a la izquierda, barra, valor a la derecha. */
export function BarList({ rows, caption }: { rows: BarRow[]; caption: string }) {
  const max = Math.max(...rows.map((r) => r.value), 0);
  return (
    <>
      <ul className="space-y-3" aria-hidden>
        {rows.map((row) => (
          <li
            key={row.key}
            className="grid grid-cols-[minmax(7rem,10rem)_1fr_auto] items-center gap-3 text-sm"
          >
            <span className="truncate text-right text-xs font-semibold text-ink">{row.label}</span>
            <Tip text={row.tip} className="h-5">
              {row.value > 0 && (
                <div
                  className={cx("h-full rounded-r", row.fill ?? "bg-rynx-primary")}
                  style={{ width: `${Math.max((row.value / max) * 100, 1.5)}%` }}
                />
              )}
              {row.value === 0 && <div className="h-full w-px bg-line" />}
            </Tip>
            <span className="min-w-8 text-right text-xs font-bold text-ink tabular">{row.valueText}</span>
          </li>
        ))}
      </ul>
      {/* Lo mismo como tabla, para lectores de pantalla. */}
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              <td>{row.tip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/** Columnas verticales (antigüedad de la deuda, costo por día): una barra por tramo. */
export function ColumnChart({ rows, caption }: { rows: BarRow[]; caption: string }) {
  const max = Math.max(...rows.map((r) => r.value), 0);
  return (
    <>
      <div className="flex h-56 items-end gap-4 border-b border-gray-300 px-2" aria-hidden>
        {rows.map((row) => (
          <Tip key={row.key} text={row.tip} className="flex h-full flex-1 flex-col justify-end">
            <span className="mb-1 text-center text-xs font-bold text-ink tabular">{row.valueText}</span>
            <div
              className={cx("rounded-t", row.value > 0 ? (row.fill ?? "bg-rynx-primary") : "bg-transparent")}
              style={{ height: `${max > 0 ? Math.max((row.value / max) * 100, row.value > 0 ? 2 : 0) : 0}%` }}
            />
          </Tip>
        ))}
      </div>
      <div className="mt-2 flex gap-4 px-2" aria-hidden>
        {rows.map((row) => (
          <span key={row.key} className="flex-1 text-center text-[11px] font-semibold text-ink">
            {row.label}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              <td>{row.tip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
