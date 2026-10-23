/**
 * Piezas visuales chicas que se reusan en todas las pantallas, con el diseño
 * de Rynx: tarjetas muy redondeadas, botones verde de la marca, campos altos.
 *
 * Están todas juntas porque son simples. Las más grandes (tabla, pasos, rango
 * de montos, panel lateral) tienen su propio archivo.
 */
import { AlertTriangle, Info, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { errorMessage, isTransient } from "@/lib/api";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- botón

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary:
    "bg-rynx-primary text-white shadow-sm hover:bg-rynx-primary-hover disabled:bg-rynx-primary/40",
  secondary:
    "border border-gray-300 bg-white text-rynx-primary hover:bg-sunken disabled:text-muted",
  ghost: "text-muted hover:bg-sunken hover:text-ink",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700 disabled:bg-red-600/40",
};

/** El estilo de botón, para usarlo también en links (`<Link className={buttonClass()}>`). */
export function buttonClass(variant: ButtonVariant = "primary", className?: string): string {
  return cx(
    "inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed",
    BUTTON_STYLES[variant],
    className,
  );
}

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
      className={buttonClass(variant, className)}
    >
      {loading && <Loader2 aria-hidden className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- encabezado de pantalla

/** Título de la pantalla con su bajada, como en todas las pantallas de Rynx. */
export function PageHeader({
  title,
  subtitle,
  actions,
  back,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  back?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {back}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[28px] leading-tight font-bold text-ink">{title}</h1>
          {subtitle && <p className="mt-1 text-[15px] text-muted">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
      </div>
    </header>
  );
}

// ---------------------------------------------------------------- tarjetas

/** Tarjeta blanca con borde y esquinas redondeadas (el "card" de Rynx). */
export function Card({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article" | "aside";
}) {
  return (
    <Tag className={cx("rounded-[var(--radius-card)] border border-line bg-surface shadow-sm", className)}>
      {children}
    </Tag>
  );
}

/** Tarjeta con título verde (como "Información general" en el editor de reglas). */
export function Panel({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cx("p-6", className)}>
      {title && (
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-rynx-primary">{title}</h2>
            {description && <p className="mt-1 text-xs text-muted">{description}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </Card>
  );
}

/** Indicador de la fila de arriba (KPI): ícono, nombre, ayuda y número grande. */
export function KpiCard({
  label,
  value,
  icon,
  hint,
  detail,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: string;
  detail?: ReactNode;
}) {
  return (
    <Card as="div" className="px-5 py-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          {icon && <span className="text-ink [&_svg]:size-5">{icon}</span>}
          <p className="text-[11px] leading-tight font-bold text-ink">{label}</p>
        </div>
        {hint && <InfoHint text={hint} />}
      </div>
      <p className="mt-3 text-[22px] font-bold text-ink tabular">{value}</p>
      {detail && <p className="mt-1 text-xs text-muted">{detail}</p>}
    </Card>
  );
}

/** El ícono (i) con su explicación al pasar el mouse o con el teclado. */
export function InfoHint({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button type="button" aria-label={text} className="rounded-full text-ink/70 hover:text-ink">
        <Info aria-hidden className="size-[18px]" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute top-6 right-0 z-20 hidden w-56 rounded-lg bg-rynx-dark px-3 py-2 text-xs text-white shadow-lg group-focus-within:block group-hover:block"
      >
        {text}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------- pestañas

/** Pestañas tipo "pastilla" de Rynx (General / Casos / ..., Mi cuenta / Organización). */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-2xl bg-sunken p-1.5">
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={cx(
              "rounded-xl px-6 py-2 text-sm font-semibold transition-colors",
              active ? "bg-rynx-primary text-white shadow-sm" : "text-ink hover:bg-white/70",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
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
      className="flex flex-wrap items-center gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger"
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
    <div className="rounded-2xl border border-dashed border-gray-300 px-6 py-10 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- formularios

/** Estilo de los campos de texto y listas desplegables. */
export function inputClass(invalid = false, className?: string): string {
  return cx(
    "w-full rounded-xl border bg-white px-4 py-2.5 text-sm placeholder:text-gray-400 disabled:bg-sunken disabled:text-muted",
    invalid ? "border-danger" : "border-gray-300",
    className,
  );
}

/**
 * Un campo con su etiqueta, una ayuda opcional y el error. El error queda
 * conectado al campo (aria-describedby) para que lo lean los lectores de pantalla.
 */
export function Field({
  id,
  label,
  hint,
  error,
  children,
  className,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  children: (props: { id: string; "aria-invalid": boolean; "aria-describedby"?: string }) => ReactNode;
  className?: string;
}) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ");
  return (
    <div className={className}>
      <label htmlFor={id} className="text-xs font-bold text-ink">
        {label}
      </label>
      <div className="mt-1.5">
        {children({ id, "aria-invalid": Boolean(error), "aria-describedby": describedBy || undefined })}
      </div>
      {hint && !error && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** Interruptor (como "Activar avisos" o el estado de un usuario en Rynx). */
export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-rynx-primary" : "bg-gray-300",
      )}
    >
      <span
        aria-hidden
        className={cx(
          "inline-block size-4 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-6" : "translate-x-1",
        )}
      />
    </button>
  );
}

// ---------------------------------------------------------------- datos

/** Un par "etiqueta: valor" en una línea, como en el detalle del caso de Rynx. */
export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <dt className="text-sm text-ink">{label}:</dt>
      <dd className="text-right text-sm text-ink">{children}</dd>
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
