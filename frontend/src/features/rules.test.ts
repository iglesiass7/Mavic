import { describe, expect, it } from "vitest";

import {
  EMPTY_RULE_FORM,
  describeConditions,
  describeTerms,
  formToRule,
  ruleToForm,
  toRuleInput,
  type RuleForm,
} from "./rules";
import type { Rule } from "@/lib/types";

// Una de las reglas de ejemplo de seed-demo, tal como la devuelve el backend.
const SHORT_TERM: Rule = {
  id: "aa71dfd4-184f-48cd-a048-1b9523a9159d",
  name: "Pago total corto plazo",
  description: "Mora de 15 a 59 días: descuento por pago total o hasta 3 cuotas.",
  min_amount: "0.00",
  max_amount: "500000.00",
  min_debt_age_days: 15,
  max_debt_age_days: 59,
  min_invoice_count: 1,
  max_invoice_count: 12,
  discount_pct: "10.00",
  payment_days: 5,
  max_installments: 3,
  interest_pct: "8.00",
  is_active: true,
};

const text = (lines: { label: string; value: string }[]) =>
  lines.map((l) => `${l.label}: ${l.value}`.replace(/ /g, " "));

describe("la regla en palabras", () => {
  it("a qué casos se aplica", () => {
    expect(text(describeConditions(SHORT_TERM))).toEqual([
      "Deuda: hasta $ 500.000",
      "Atraso: de 15 días a 59 días",
      "Facturas: hasta 12",
    ]);
  });

  it("sin topes", () => {
    const rule = { ...SHORT_TERM, min_amount: "500000.01", max_amount: null, max_invoice_count: null, max_debt_age_days: null };
    expect(text(describeConditions(rule))).toEqual([
      "Deuda: desde $ 500.000,01",
      "Atraso: desde 15 días",
      "Facturas: cualquiera",
    ]);
  });

  it("qué puede ofrecer el agente", () => {
    expect(text(describeTerms(SHORT_TERM))).toEqual([
      "Pago único: 10 % de descuento, a pagar en 5 días",
      "Cuotas: 3 cuotas con 8 % de interés total",
    ]);
    expect(
      text(describeTerms({ ...SHORT_TERM, discount_pct: "0.00", max_installments: 1 })),
    ).toEqual(["Pago único: sin descuento, a pagar en 5 días", "Cuotas: no ofrece cuotas"]);
  });
});

describe("formulario de regla", () => {
  const form = (changes: Partial<RuleForm>): RuleForm => ({ ...EMPTY_RULE_FORM, name: "Prueba", ...changes });

  it("ida y vuelta: una regla del backend se edita y se guarda igual", () => {
    const { rule, errors } = formToRule(ruleToForm(SHORT_TERM));
    expect(errors).toEqual({});
    // Los montos vuelven como texto equivalente ("500000" en vez de "500000.00").
    expect(rule).toEqual({
      ...toRuleInput(SHORT_TERM),
      min_amount: "0",
      max_amount: "500000",
      discount_pct: "10",
      interest_pct: "8",
    });
  });

  it("entiende la forma argentina de escribir números", () => {
    const { rule } = formToRule(
      form({ max_amount: "1.250.000,50", discount_pct: "12,5", max_installments: "6", interest_pct: "7,25" }),
    );
    expect(rule).toMatchObject({ max_amount: "1250000.50", discount_pct: "12.5", interest_pct: "7.25" });
  });

  it("vacío en 'hasta' = sin tope", () => {
    const { rule } = formToRule(form({ max_amount: "", max_debt_age_days: "", max_invoice_count: "" }));
    expect(rule).toMatchObject({ max_amount: null, max_debt_age_days: null, max_invoice_count: null });
  });

  it("con 1 cuota, el interés se manda en 0", () => {
    const { rule } = formToRule(form({ max_installments: "1", interest_pct: "15" }));
    expect(rule?.interest_pct).toBe("0");
  });

  it("marca cada error en su campo, con los límites del backend", () => {
    const { rule, errors } = formToRule(
      form({
        name: "  ",
        min_amount: "1.000",
        max_amount: "500",
        min_debt_age_days: "30",
        max_debt_age_days: "10",
        min_invoice_count: "0",
        discount_pct: "100",
        interest_pct: "100,5",
        max_installments: "37",
        payment_days: "0",
      }),
    );
    expect(rule).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(
      [
        "name",
        "max_amount",
        "max_debt_age_days",
        "min_invoice_count",
        "discount_pct",
        "interest_pct",
        "max_installments",
        "payment_days",
      ].sort(),
    );
  });
});
