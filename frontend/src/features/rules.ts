/**
 * Reglas de negociación: pedidos al backend, resumen en palabras y el
 * formulario (texto que escribe la persona <-> regla que entiende el backend).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { formatMoneyShort, formatPercent } from "@/lib/format";
import { compareDecimals, decimalToInput, parseDecimalInput, parseIntegerInput } from "@/lib/numbers";
import type { Rule, RuleInput } from "@/lib/types";

// Los mismos límites que valida el backend (negotiation/domain/rules.py).
export const MAX_INSTALLMENTS = 36;
export const MAX_PAYMENT_DAYS = 90;

// ---------------------------------------------------------------- pedidos

export function useRules() {
  return useQuery({
    queryKey: ["rules"],
    queryFn: ({ signal }) => apiFetch<Rule[]>("/negotiation-rules", { signal }),
  });
}

/** Crea (sin id) o reemplaza (con id) una regla. */
export function useSaveRule(ruleId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (rule: RuleInput) =>
      ruleId
        ? apiFetch<Rule>(`/negotiation-rules/${ruleId}`, { method: "PUT", json: rule })
        : apiFetch<Rule>("/negotiation-rules", { method: "POST", json: rule }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["rules"] }),
        // Cambiar una regla cambia lo que el agente puede ofrecer en cada caso.
        queryClient.invalidateQueries({ queryKey: ["case"] }),
      ]),
  });
}

/** La regla como se manda al backend: todo menos el id. */
export function toRuleInput(rule: Rule): RuleInput {
  const input: Partial<Rule> = { ...rule };
  delete input.id;
  return input as RuleInput;
}

// ---------------------------------------------------------------- resumen en palabras

function range(min: string, max: string | null, lowest: string, show: (v: string) => string): string {
  const fromLowest = min === lowest;
  if (fromLowest && max === null) return "cualquiera";
  if (fromLowest) return `hasta ${show(max!)}`;
  if (max === null) return `desde ${show(min)}`;
  if (min === max) return show(min);
  return `de ${show(min)} a ${show(max)}`;
}

/** A qué casos se aplica, una línea por condición. */
export function describeConditions(rule: Rule): { label: string; value: string }[] {
  const days = (v: string) => (v === "1" ? "1 día" : `${v} días`);
  return [
    {
      label: "Deuda",
      value: range(rule.min_amount.replace(/\.0+$/, ""), rule.max_amount, "0", formatMoneyShort),
    },
    {
      label: "Atraso",
      value: range(
        String(rule.min_debt_age_days),
        rule.max_debt_age_days === null ? null : String(rule.max_debt_age_days),
        "0",
        days,
      ),
    },
    {
      label: "Facturas",
      value: range(
        String(rule.min_invoice_count),
        rule.max_invoice_count === null ? null : String(rule.max_invoice_count),
        "1",
        (v) => v,
      ),
    },
  ];
}

const isZero = (pct: string) => /^0+(\.0+)?$/.test(pct);

/** Qué puede ofrecer el agente con esta regla. */
export function describeTerms(rule: Rule): { label: string; value: string }[] {
  const days = rule.payment_days === 1 ? "1 día" : `${rule.payment_days} días`;
  return [
    {
      label: "Pago único",
      value: `${isZero(rule.discount_pct) ? "sin descuento" : `${formatPercent(rule.discount_pct)} de descuento`}, a pagar en ${days}`,
    },
    {
      label: "Cuotas",
      value:
        rule.max_installments === 1
          ? "no ofrece cuotas"
          : `${rule.max_installments} cuotas ${isZero(rule.interest_pct) ? "sin interés" : `con ${formatPercent(rule.interest_pct)} de interés total`}`,
    },
  ];
}

// ---------------------------------------------------------------- formulario

/** El formulario guarda todo como texto, tal cual lo escribe la persona. */
export interface RuleForm {
  name: string;
  description: string;
  min_amount: string;
  max_amount: string;
  min_debt_age_days: string;
  max_debt_age_days: string;
  min_invoice_count: string;
  max_invoice_count: string;
  discount_pct: string;
  payment_days: string;
  max_installments: string;
  interest_pct: string;
  is_active: boolean;
}

export type RuleFormErrors = Partial<Record<keyof RuleForm, string>>;

export const EMPTY_RULE_FORM: RuleForm = {
  name: "",
  description: "",
  min_amount: "0",
  max_amount: "",
  min_debt_age_days: "0",
  max_debt_age_days: "",
  min_invoice_count: "1",
  max_invoice_count: "",
  discount_pct: "0",
  payment_days: "5",
  max_installments: "1",
  interest_pct: "0",
  is_active: true,
};

export function ruleToForm(rule: Rule): RuleForm {
  const optional = (v: number | null) => (v === null ? "" : String(v));
  return {
    name: rule.name,
    description: rule.description,
    min_amount: decimalToInput(rule.min_amount),
    max_amount: rule.max_amount === null ? "" : decimalToInput(rule.max_amount),
    min_debt_age_days: String(rule.min_debt_age_days),
    max_debt_age_days: optional(rule.max_debt_age_days),
    min_invoice_count: String(rule.min_invoice_count),
    max_invoice_count: optional(rule.max_invoice_count),
    discount_pct: decimalToInput(rule.discount_pct),
    payment_days: String(rule.payment_days),
    max_installments: String(rule.max_installments),
    interest_pct: decimalToInput(rule.interest_pct),
    is_active: rule.is_active,
  };
}

/**
 * Revisa el formulario y, si está bien, arma la regla para el backend.
 * Son las mismas reglas que valida el backend, pero acá se dicen campo por
 * campo y en el idioma del formulario. El backend vuelve a validar todo.
 */
export function formToRule(form: RuleForm): { rule: RuleInput | null; errors: RuleFormErrors } {
  const errors: RuleFormErrors = {};
  const MONEY = "Escribí un monto, por ejemplo 500.000 o 1.250,50.";
  const WHOLE = "Escribí un número entero.";

  const name = form.name.trim();
  if (!name) errors.name = "La regla necesita un nombre.";
  else if (name.length > 80) errors.name = "Máximo 80 caracteres.";
  if (form.description.trim().length > 500) errors.description = "Máximo 500 caracteres.";

  // ---- rangos: "hasta" vacío = sin tope
  const minAmount = parseDecimalInput(form.min_amount || "0");
  const maxAmount = form.max_amount.trim() ? parseDecimalInput(form.max_amount) : null;
  if (minAmount === null) errors.min_amount = MONEY;
  if (form.max_amount.trim() && maxAmount === null) errors.max_amount = MONEY;
  if (minAmount !== null && maxAmount !== null && compareDecimals(maxAmount, minAmount) < 0) {
    errors.max_amount = "Tiene que ser mayor o igual que el mínimo.";
  }

  function intRange(minKey: keyof RuleForm, maxKey: keyof RuleForm, lowest: number) {
    const minText = String(form[minKey]);
    const maxText = String(form[maxKey]).trim();
    const min = parseIntegerInput(minText || String(lowest));
    const max = maxText ? parseIntegerInput(maxText) : null;
    if (min === null) errors[minKey] = WHOLE;
    else if (min < lowest) errors[minKey] = `El mínimo es ${lowest}.`;
    if (maxText && max === null) errors[maxKey] = WHOLE;
    if (min !== null && max !== null && max < min) errors[maxKey] = "Tiene que ser mayor o igual que el mínimo.";
    return [min ?? lowest, max] as const;
  }
  const [minDays, maxDays] = intRange("min_debt_age_days", "max_debt_age_days", 0);
  const [minInvoices, maxInvoices] = intRange("min_invoice_count", "max_invoice_count", 1);

  // ---- condiciones de pago
  const discount = parseDecimalInput(form.discount_pct || "0");
  if (discount === null || compareDecimals(discount, "100") >= 0) {
    errors.discount_pct = "Entre 0 y 99,99 %.";
  }
  const interest = parseDecimalInput(form.interest_pct || "0");
  if (interest === null || compareDecimals(interest, "100") > 0) {
    errors.interest_pct = "Entre 0 y 100 %.";
  }
  const installments = parseIntegerInput(form.max_installments);
  if (installments === null || installments < 1 || installments > MAX_INSTALLMENTS) {
    errors.max_installments = `Entre 1 y ${MAX_INSTALLMENTS}.`;
  }
  const paymentDays = parseIntegerInput(form.payment_days);
  if (paymentDays === null || paymentDays < 1 || paymentDays > MAX_PAYMENT_DAYS) {
    errors.payment_days = `Entre 1 y ${MAX_PAYMENT_DAYS} días.`;
  }

  if (Object.keys(errors).length > 0) return { rule: null, errors };
  return {
    errors,
    rule: {
      name,
      description: form.description.trim(),
      min_amount: minAmount!,
      max_amount: maxAmount,
      min_debt_age_days: minDays,
      max_debt_age_days: maxDays,
      min_invoice_count: minInvoices,
      max_invoice_count: maxInvoices,
      discount_pct: discount!,
      payment_days: paymentDays!,
      max_installments: installments!,
      // Sin cuotas, el interés no se usa: se manda 0 para que la regla quede clara.
      interest_pct: installments === 1 ? "0" : interest!,
      is_active: form.is_active,
    },
  };
}
