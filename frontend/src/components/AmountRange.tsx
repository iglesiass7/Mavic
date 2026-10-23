"use client";

/**
 * "Rango de monto" de Rynx: una barra con dos puntos (mínimo y máximo).
 *
 * El tope (`max`) lo da el backend: el monto más alto de lo que se está viendo.
 * Mientras se arrastra se muestra el valor; el filtro se aplica al soltar, para
 * no pedirle al backend una página por cada pixel.
 */
import { useState } from "react";

import { formatMoney } from "@/lib/format";

/** El rango elegido: `null` en un extremo significa "sin límite de ese lado". */
export interface Range {
  min: number | null;
  max: number | null;
}

/** Paso de la barra: unas 100 posiciones entre 0 y el tope, en números redondos. */
export function stepFor(max: number): number {
  if (max <= 0) return 1;
  const raw = max / 100;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  return Math.max(1, Math.ceil(raw / magnitude) * magnitude);
}

export function AmountRange({
  max,
  value,
  onChange,
  label = "Rango de monto",
}: {
  max: number; // el monto más alto
  value: Range;
  onChange: (range: Range) => void;
  label?: string;
}) {
  const step = stepFor(max);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const [draft, setDraft] = useState({ min: value.min ?? 0, max: value.max ?? top });

  // Si cambia el tope (otro grupo, otra búsqueda) o se borran los filtros, se
  // reacomoda. Se ajusta durante el render (el patrón que recomienda React para
  // "estado que depende de una prop"), no en un efecto: así no hay un render de más.
  const source = `${value.min}|${value.max}|${top}`;
  const [seen, setSeen] = useState(source);
  if (seen !== source) {
    setSeen(source);
    setDraft({ min: value.min ?? 0, max: value.max ?? top });
  }

  function commit(next: { min: number; max: number }) {
    onChange({ min: next.min <= 0 ? null : next.min, max: next.max >= top ? null : next.max });
  }

  const left = (draft.min / top) * 100;
  const right = (draft.max / top) * 100;

  return (
    <fieldset className="min-w-64">
      <legend className="text-xs font-bold text-ink">{label}</legend>
      <div className="mt-2 flex items-center gap-3">
        <span className="text-sm font-semibold tabular">{formatMoney(String(draft.min))}</span>
        <div className="relative h-5 flex-1">
          <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-gray-200" />
          <div
            className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-rynx-primary"
            style={{ left: `${left}%`, right: `${100 - right}%` }}
          />
          <input
            type="range"
            aria-label="Monto mínimo"
            min={0}
            max={top}
            step={step}
            value={draft.min}
            onChange={(event) =>
              setDraft((d) => ({ ...d, min: Math.min(Number(event.target.value), d.max) }))
            }
            onPointerUp={() => commit(draft)}
            onKeyUp={() => commit(draft)}
            className="range-thumb pointer-events-none absolute inset-0 w-full appearance-none bg-transparent"
          />
          <input
            type="range"
            aria-label="Monto máximo"
            min={0}
            max={top}
            step={step}
            value={draft.max}
            onChange={(event) =>
              setDraft((d) => ({ ...d, max: Math.max(Number(event.target.value), d.min) }))
            }
            onPointerUp={() => commit(draft)}
            onKeyUp={() => commit(draft)}
            className="range-thumb pointer-events-none absolute inset-0 w-full appearance-none bg-transparent"
          />
        </div>
        <span className="text-sm font-semibold tabular">{formatMoney(String(draft.max))}</span>
      </div>
    </fieldset>
  );
}
