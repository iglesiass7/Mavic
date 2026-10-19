/**
 * Piezas visuales chicas que se reusan en todas las pantallas.
 *
 * Están todas juntas porque son pocas y simples. Si crecen, cada una pasa a su
 * propio archivo.
 */
import { AlertTriangle, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { errorMessage, isTransient } from "@/lib/api";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- botón

type ButtonVariant = "primary" | "secondary" | "ghost";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-petrol text-white hover:bg-petrol-dark disabled:bg-petrol/50",
  secondary:
    "border border-line bg-surface text-ink hover:border-petrol hover:text-petrol disabled:text-muted",
  ghost: "text-muted hover:text-ink",
};

export function Button({
  variant = "primary",
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean }) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed",
        BUTTON_STYLES[variant],
        className,
      )}
    >
      {loading && <Loader2 aria-hidden className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- panel

export function Panel({
  title,
  action,
  children,
  className,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)}>
      {title && (
        <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------- estados de carga

export function LoadingState({ label = "Cargando…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-10 text-sm text-muted">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-md border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger"
    >
      <AlertTriangle aria-hidden className="size-4 shrink-0" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Reintentar
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- datos

/** Un par "etiqueta: valor", para fichas como la del deudor. */
export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{children}</dd>
    </div>
  );
}

/**
 * Error de un pedido al backend. Ofrece "Reintentar" solo cuando tiene sentido
 * (sin conexión o falla del servidor); si el caso no existe, reintentar no sirve.
 */
export function QueryError({ error, retry }: { error: unknown; retry: () => unknown }) {
  return (
    <ErrorState
      message={errorMessage(error)}
      onRetry={isTransient(error) ? () => void retry() : undefined}
    />
  );
}

export { cx };
