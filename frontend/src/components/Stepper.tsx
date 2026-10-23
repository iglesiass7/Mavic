/**
 * Pasos en círculos unidos por una línea, como en Rynx:
 *
 *    (⇧)──────────────(🛡)──────────────(✓)
 *   Subir            Validar           Cargar
 *
 * Sirve para un proceso (la carga de facturas: el paso actual y los hechos) y
 * para elegir un grupo (las facturas: cada círculo es un botón).
 */
import type { LucideIcon } from "lucide-react";

import { cx } from "./ui";

export interface Step<T extends string> {
  value: T;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  badge?: number; // un número al lado del título (ej. cuántas facturas hay)
}

export function Stepper<T extends string>({
  steps,
  current,
  done = [],
  onSelect,
  label,
}: {
  steps: Step<T>[];
  current: T;
  done?: T[];
  onSelect?: (value: T) => void; // si está, cada paso es un botón
  label: string;
}) {
  return (
    <nav aria-label={label} className="mb-6">
      <ol className="flex items-start">
        {steps.map((step, index) => {
          const active = step.value === current;
          const complete = done.includes(step.value);
          const Icon = step.icon;
          const circle = (
            <>
              <span
                className={cx(
                  "flex size-14 items-center justify-center rounded-full border-2 transition-colors sm:size-16",
                  // Un solo color de fondo por estado: dos clases bg-* juntas se pisan.
                  complete && !active
                    ? "border-rynx-primary bg-rynx-primary text-white"
                    : active
                      ? "border-rynx-primary bg-white text-rynx-primary"
                      : "border-gray-300 bg-white text-gray-400",
                )}
              >
                <Icon aria-hidden className="size-6 sm:size-7" />
              </span>
              <span
                className={cx(
                  "mt-2 block text-sm font-bold sm:text-base",
                  active || complete ? "text-rynx-primary" : "text-gray-500",
                )}
              >
                {step.title}
                {step.badge !== undefined && (
                  <span className="ml-1.5 rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink tabular">
                    {step.badge}
                  </span>
                )}
              </span>
              <span className="block text-[11px] text-muted sm:text-xs">{step.subtitle}</span>
            </>
          );
          return (
            <li key={step.value} className={cx("flex items-start", index > 0 && "flex-1")}>
              {index > 0 && <span aria-hidden className="mx-2 mt-7 h-0.5 flex-1 bg-gray-300 sm:mt-8 sm:mx-4" />}
              <div
                className={cx(
                  "flex flex-col text-center",
                  index === 0 ? "items-start text-left" : index === steps.length - 1 ? "items-end text-right" : "items-center",
                )}
              >
                {onSelect ? (
                  <button
                    type="button"
                    aria-current={active ? "step" : undefined}
                    onClick={() => onSelect(step.value)}
                    className={cx(
                      "flex flex-col rounded-2xl p-1",
                      index === 0 ? "items-start" : index === steps.length - 1 ? "items-end" : "items-center",
                    )}
                  >
                    {circle}
                  </button>
                ) : (
                  <div
                    aria-current={active ? "step" : undefined}
                    className={cx(
                      "flex flex-col",
                      index === 0 ? "items-start" : index === steps.length - 1 ? "items-end" : "items-center",
                    )}
                  >
                    {circle}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
