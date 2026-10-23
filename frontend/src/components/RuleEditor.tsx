"use client";

/**
 * Formulario para crear o editar una regla. A la derecha, la regla en palabras
 * tal como va a quedar: así se ve el efecto antes de guardar.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { RuleSummary } from "@/components/RuleSummary";
import { Button, ErrorState, Field, Panel, buttonClass, inputClass } from "@/components/ui";
import {
  EMPTY_RULE_FORM,
  MAX_INSTALLMENTS,
  MAX_PAYMENT_DAYS,
  formToRule,
  ruleToForm,
  useSaveRule,
  type RuleForm,
  type RuleFormErrors,
} from "@/features/rules";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/types";

/** Un campo de texto con una unidad al costado ("$", "días", "%"). */
function UnitInput({
  value,
  onChange,
  prefix,
  suffix,
  placeholder,
  invalid,
  ...aria
}: {
  value: string;
  onChange: (value: string) => void;
  prefix?: string;
  suffix?: string;
  placeholder?: string;
  invalid: boolean;
  id: string;
  "aria-invalid": boolean;
  "aria-describedby"?: string;
}) {
  return (
    <div className="relative">
      {prefix && (
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted">
          {prefix}
        </span>
      )}
      <input
        {...aria}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={inputClass(invalid, prefix ? "pl-7" : suffix ? "pr-14" : undefined)}
      />
      {suffix && (
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted">
          {suffix}
        </span>
      )}
    </div>
  );
}

function RangeRow({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-[minmax(0,10rem)_1fr_1fr]">
      <legend className="sr-only">{title}</legend>
      <div className="col-span-2 sm:col-span-1 sm:pt-7">
        <p className="text-sm font-medium" aria-hidden>
          {title}
        </p>
        <p className="text-xs text-muted">{hint}</p>
      </div>
      {children}
    </fieldset>
  );
}

export function RuleEditor({ rule }: { rule?: Rule }) {
  const router = useRouter();
  const [form, setForm] = useState<RuleForm>(rule ? ruleToForm(rule) : EMPTY_RULE_FORM);
  const [errors, setErrors] = useState<RuleFormErrors>({});
  const save = useSaveRule(rule?.id);

  const set = (key: keyof RuleForm) => (value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));

  // La vista previa usa la misma conversión que el guardado: si se puede leer, se muestra.
  const preview = formToRule(form).rule;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const result = formToRule(form);
    setErrors(result.errors);
    if (!result.rule) return;
    save.mutate(result.rule, { onSuccess: () => router.push("/rules?tramo=moroso") });
  }

  const noInstallments = form.max_installments.trim() === "1";

  const field = (
    key: keyof RuleForm,
    label: string,
    options: { prefix?: string; suffix?: string; placeholder?: string; hint?: ReactNode } = {},
  ) => (
    <Field id={key} label={label} hint={options.hint} error={errors[key]}>
      {(aria) => (
        <UnitInput
          {...aria}
          value={String(form[key])}
          onChange={set(key)}
          invalid={Boolean(errors[key])}
          prefix={options.prefix}
          suffix={options.suffix}
          placeholder={options.placeholder}
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={handleSubmit} noValidate className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-6">
        <Panel>
          <div className="space-y-4">
            <Field id="name" label="Nombre" error={errors.name}>
              {(aria) => (
                <input
                  {...aria}
                  value={form.name}
                  onChange={(e) => set("name")(e.target.value)}
                  maxLength={80}
                  className={inputClass(Boolean(errors.name))}
                />
              )}
            </Field>
            <Field
              id="description"
              label="Descripción (opcional)"
              hint="Para el equipo: cuándo y por qué se usa."
              error={errors.description}
            >
              {(aria) => (
                <textarea
                  {...aria}
                  value={form.description}
                  onChange={(e) => set("description")(e.target.value)}
                  rows={2}
                  maxLength={500}
                  className={inputClass(Boolean(errors.description))}
                />
              )}
            </Field>
          </div>
        </Panel>

        <Panel title="A qué casos se aplica">
          <div className="space-y-5">
            <RangeRow title="Deuda" hint="Total de las facturas del caso.">
              {field("min_amount", "Desde", { prefix: "$" })}
              {field("max_amount", "Hasta", { prefix: "$", placeholder: "Sin tope" })}
            </RangeRow>
            <RangeRow title="Días de atraso" hint="Desde la factura más vieja.">
              {field("min_debt_age_days", "Desde", { suffix: "días" })}
              {field("max_debt_age_days", "Hasta", { suffix: "días", placeholder: "Sin tope" })}
            </RangeRow>
            <RangeRow title="Facturas" hint="Cuántas tiene el caso.">
              {field("min_invoice_count", "Desde")}
              {field("max_invoice_count", "Hasta", { placeholder: "Sin tope" })}
            </RangeRow>
          </div>
        </Panel>

        <Panel title="Qué puede ofrecer el agente">
          <div className="grid gap-5 sm:grid-cols-2">
            {field("discount_pct", "Descuento por pago único", {
              suffix: "%",
              hint: "0 = sin descuento.",
            })}
            {field("payment_days", "Plazo para pagar", {
              suffix: "días",
              hint: `También es el vencimiento de la primera cuota. Hasta ${MAX_PAYMENT_DAYS}.`,
            })}
            {field("max_installments", "Cuotas", {
              hint: `1 = solo pago único. Hasta ${MAX_INSTALLMENTS}.`,
            })}
            <Field
              id="interest_pct"
              label="Interés total del plan en cuotas"
              hint={noInstallments ? "Con 1 cuota no se usa." : "Se suma una sola vez al total, no por cuota."}
              error={errors.interest_pct}
            >
              {(aria) => (
                <div className="relative">
                  <input
                    {...aria}
                    type="text"
                    inputMode="decimal"
                    value={noInstallments ? "0" : form.interest_pct}
                    disabled={noInstallments}
                    onChange={(e) => set("interest_pct")(e.target.value)}
                    className={inputClass(Boolean(errors.interest_pct), "pr-14")}
                  />
                  <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted">
                    %
                  </span>
                </div>
              )}
            </Field>
          </div>
        </Panel>

        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => set("is_active")(e.target.checked)}
            className="mt-0.5 size-4 accent-petrol"
          />
          <span>
            <span className="font-medium">Activa</span>
            <span className="block text-muted">
              Si está desactivada, el agente no la usa y no se controla que se pise con otras.
            </span>
          </span>
        </label>

        {save.isError && <ErrorState message={errorMessage(save.error)} />}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" loading={save.isPending}>
            {rule ? "Guardar cambios" : "Crear regla"}
          </Button>
          <Link href="/rules?tramo=moroso" className={buttonClass("ghost")}>
            Cancelar
          </Link>
        </div>
      </div>

      <aside className="rounded-2xl border border-petrol/25 bg-petrol-soft p-5 lg:sticky lg:top-8">
        <p className="font-semibold">Así queda la regla</p>
        {preview ? (
          <div className="mt-4 [&_.grid]:grid-cols-1">
            <RuleSummary rule={{ id: "preview", ...preview }} />
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted">
            Completá los datos y acá vas a ver la regla en palabras.
          </p>
        )}
      </aside>
    </form>
  );
}
