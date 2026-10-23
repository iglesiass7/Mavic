"use client";

/**
 * Medidor de costos, con el diseño de Rynx: indicadores arriba, la tabla por
 * concepto y el costo de cada día.
 *
 *   uso real del mes (minutos de llamada, emails, WhatsApp)  ×  tarifas de la empresa
 *
 * En Rynx los montos de esta pantalla estaban escritos en el código. Acá salen
 * del uso real (ADR-039). El mes vive en la dirección (?mes=2026-10).
 */
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Gauge,
  LayoutGrid,
  Pencil,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { ChartCard, ColumnChart } from "@/components/Charts";
import { Sheet } from "@/components/Sheet";
import {
  Button,
  Card,
  ErrorState,
  Field,
  KpiCard,
  LoadingState,
  PageHeader,
  QueryError,
  cx,
  inputClass,
} from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  BUDGET_LABEL,
  CONCEPT_LABEL,
  CONCEPT_UNIT,
  currentMonth,
  monthName,
  shiftMonth,
  useCostRates,
  useMonthCosts,
  useSaveCostRates,
} from "@/features/costs";
import { errorMessage } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { parseDecimalInput } from "@/lib/numbers";
import type { BudgetStatus, CostConcept, CostRates, MonthCosts } from "@/lib/types";

const BUDGET_STYLE: Record<BudgetStatus, string> = {
  no_budget: "text-muted",
  ok: "text-status-agreement",
  high: "text-status-escalated",
  over_projection: "text-status-disputed",
  over_budget: "text-status-disputed",
};

/** "1.58" minutos -> "1,58 min"; 3 emails -> "3 emails". */
function usage(concept: CostConcept, quantity: string, count: number): string {
  if (concept === "calls") {
    const minutes = Number(quantity).toLocaleString("es-AR", { maximumFractionDigits: 2 });
    return `${minutes} min · ${count === 1 ? "1 llamada" : `${count} llamadas`}`;
  }
  const noun = concept === "email" ? ["email", "emails"] : ["mensaje", "mensajes"];
  return `${count} ${count === 1 ? noun[0] : noun[1]}`;
}

function RatesForm({ rates, onDone }: { rates: CostRates; onDone: () => void }) {
  const save = useSaveCostRates();
  const decimal = (value: string) => value.replace(".", ",");
  const [form, setForm] = useState({
    currency: rates.currency,
    call_minute: decimal(rates.call_minute),
    email: decimal(rates.email),
    whatsapp: decimal(rates.whatsapp),
    monthly_budget: rates.monthly_budget ? decimal(rates.monthly_budget) : "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    const parsed: Record<string, string | null> = {};
    for (const key of ["call_minute", "email", "whatsapp"] as const) {
      // Una tarifa nunca llega a mil: "0.001" es cero coma cero cero uno, no mil.
      const text = form[key].includes(",") ? form[key] : form[key].replace(".", ",");
      const value = parseDecimalInput(text || "0", 4);
      if (value === null) found[key] = "Escribí un número (ej. 0,12).";
      parsed[key] = value;
    }
    let budget: string | null = null;
    if (form.monthly_budget.trim()) {
      budget = parseDecimalInput(form.monthly_budget, 2);
      if (budget === null || Number(budget) <= 0)
        found.monthly_budget = "Escribí un monto mayor que 0, o dejalo vacío.";
    }
    if (!/^[A-Za-z]{3}$/.test(form.currency.trim())) found.currency = "3 letras: USD, ARS…";
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    save.mutate(
      {
        currency: form.currency.trim().toUpperCase(),
        call_minute: parsed.call_minute!,
        email: parsed.email!,
        whatsapp: parsed.whatsapp!,
        monthly_budget: budget,
      },
      { onSuccess: onDone },
    );
  }

  const input = (key: keyof typeof form, label: string, hint: string) => (
    <Field id={`rate-${key}`} label={label} hint={hint} error={errors[key]}>
      {(aria) => (
        <input
          {...aria}
          inputMode="decimal"
          value={form[key]}
          onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
          className={inputClass(Boolean(errors[key]))}
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <p className="text-sm text-muted">
        Lo que te cobra cada proveedor por unidad. Con esto Mavic calcula el costo del uso real. Hasta 4
        decimales.
      </p>
      {input("currency", "Moneda", "La de las tarifas (los proveedores suelen cobrar en USD).")}
      {input("call_minute", "Minuto de llamada", "ElevenLabs + Twilio, por minuto hablado.")}
      {input("email", "Email", "Por email mandado (SMTP o AWS SES).")}
      {input("whatsapp", "Mensaje de WhatsApp", "Twilio + Meta, por mensaje.")}
      {input("monthly_budget", "Tope mensual (opcional)", "Para avisar si el mes se pasa. Vacío: sin tope.")}
      {save.isError && <ErrorState message={errorMessage(save.error)} />}
      <div className="flex gap-3">
        <Button type="submit" loading={save.isPending}>
          Guardar tarifas
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

function CostsBody({ data }: { data: MonthCosts }) {
  const money = (amount: string) => formatMoney(amount, data.currency);
  const top = [...data.concepts].sort((a, b) => Number(b.cost) - Number(a.cost))[0];
  const average = data.days_counted > 0 ? (Number(data.total) / data.days_counted).toFixed(2) : "0.00";
  const current = data.days_counted > 0 && data.days_counted < data.days_in_month;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Costo acumulado"
          value={money(data.total)}
          icon={<CircleDollarSign />}
          detail={current ? `Del 1 al ${data.days_counted}` : "Todo el mes"}
          hint="El uso real del mes multiplicado por las tarifas."
        />
        <KpiCard
          label="Proyección mensual"
          value={money(data.projected_total)}
          icon={<Gauge />}
          detail={current ? "Si sigue al mismo ritmo" : "Mes cerrado: es lo gastado"}
          hint="Lo gastado hasta hoy, al mismo ritmo, hasta el último día del mes."
        />
        <KpiCard
          label="Promedio diario"
          value={money(average)}
          icon={<CalendarDays />}
          detail={`${data.days_counted} días`}
          hint="Costo acumulado dividido los días que ya pasaron del mes."
        />
        <KpiCard
          label="Concepto con mayor costo"
          value={top && Number(top.cost) > 0 ? CONCEPT_LABEL[top.concept] : "—"}
          icon={<LayoutGrid />}
          detail={top && Number(top.cost) > 0 ? money(top.cost) : "Sin consumo"}
          hint="El servicio que más gastó en el mes."
        />
      </div>

      <p className={cx("text-sm font-semibold", BUDGET_STYLE[data.budget_status])} role="status">
        {BUDGET_LABEL[data.budget_status]}
        {data.monthly_budget && ` · tope ${money(data.monthly_budget)}`}
      </p>

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <caption className="sr-only">Costos por concepto</caption>
          <thead className="bg-sunken text-left">
            <tr>
              <th scope="col" className="px-5 py-3 font-bold">
                Concepto
              </th>
              <th scope="col" className="px-5 py-3 font-bold">
                Uso
              </th>
              <th scope="col" className="px-5 py-3 font-bold">
                Tarifa
              </th>
              <th scope="col" className="px-5 py-3 text-right font-bold">
                Costo acumulado
              </th>
              <th scope="col" className="px-5 py-3 text-right font-bold">
                Proyección
              </th>
            </tr>
          </thead>
          <tbody>
            {data.concepts.map((c) => (
              <tr key={c.concept} className="border-t border-line">
                <th scope="row" className="px-5 py-3 text-left font-semibold">
                  {CONCEPT_LABEL[c.concept]}
                </th>
                <td className="px-5 py-3 text-muted">{usage(c.concept, c.quantity, c.count)}</td>
                <td className="px-5 py-3 text-muted whitespace-nowrap">
                  {money(c.rate)} {CONCEPT_UNIT[c.concept]}
                </td>
                <td className="px-5 py-3 text-right font-medium tabular">{money(c.cost)}</td>
                <td className="px-5 py-3 text-right tabular">{money(c.projected_cost)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-gray-300">
              <th scope="row" colSpan={3} className="px-5 py-3 text-left font-black text-rynx-primary">
                Total
              </th>
              <td className="px-5 py-3 text-right font-black text-rynx-primary tabular">
                {money(data.total)}
              </td>
              <td className="px-5 py-3 text-right font-black text-rynx-primary tabular">
                {money(data.projected_total)}
              </td>
            </tr>
          </tfoot>
        </table>
      </Card>

      <ChartCard title="Costo por día" footer="Pasá el mouse (o el teclado) por una barra para ver el monto.">
        <ColumnChart
          caption="Costo por día del mes"
          rows={data.daily.map((d) => ({
            key: d.day,
            label: String(Number(d.day.slice(8))),
            value: Number(d.cost),
            valueText: "",
            tip: `${d.day.slice(8)}/${d.day.slice(5, 7)}: ${money(d.cost)}`,
          }))}
        />
      </ChartCard>
    </div>
  );
}

function CostsScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const asked = useSearchParams().get("mes");
  const month = asked && /^\d{4}-(0[1-9]|1[0-2])$/.test(asked) ? asked : currentMonth();
  const costs = useMonthCosts(month);
  const rates = useCostRates();
  const me = useMe();
  const canManage = can(me.data, "manage_costs");
  const [editing, setEditing] = useState(false);
  const isCurrent = month === currentMonth();

  const go = (next: string) =>
    router.push(next === currentMonth() ? pathname : `${pathname}?mes=${next}`, { scroll: false });

  return (
    <>
      <PageHeader
        title={`Costos: ${monthName(month)}`}
        subtitle="El uso real de Mavic (llamadas, emails y WhatsApp) por las tarifas de tu empresa."
        actions={
          canManage &&
          rates.isSuccess && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil aria-hidden className="size-4" /> Editar tarifas
            </Button>
          )
        }
      />

      <nav aria-label="Mes" className="mb-6 flex items-center gap-2">
        <Button
          variant="secondary"
          className="px-3"
          onClick={() => go(shiftMonth(month, -1))}
          aria-label="Mes anterior"
        >
          <ChevronLeft aria-hidden className="size-4" />
        </Button>
        <span className="min-w-40 text-center text-sm font-bold first-letter:uppercase">
          {monthName(month)}
        </span>
        <Button
          variant="secondary"
          className="px-3"
          disabled={isCurrent}
          onClick={() => go(shiftMonth(month, 1))}
          aria-label="Mes siguiente"
        >
          <ChevronRight aria-hidden className="size-4" />
        </Button>
        {!isCurrent && (
          <Button variant="ghost" onClick={() => go(currentMonth())}>
            Volver al mes actual
          </Button>
        )}
      </nav>

      {costs.data && !costs.data.rates_configured && (
        <p className="mb-6 rounded-2xl border border-petrol/25 bg-petrol-soft px-5 py-3 text-sm">
          Todavía no se cargaron las tarifas: el uso se cuenta igual, pero los montos dan 0.{" "}
          {canManage ? "Cargalas con “Editar tarifas”." : "Las carga alguien con rol de administración."}
        </p>
      )}

      {costs.isPending && <LoadingState label="Calculando los costos…" />}
      {costs.isError && <QueryError error={costs.error} retry={costs.refetch} />}
      {costs.isSuccess && <CostsBody data={costs.data} />}

      <Sheet title="Tarifas" open={editing} onClose={() => setEditing(false)}>
        {editing && rates.data && <RatesForm rates={rates.data} onDone={() => setEditing(false)} />}
      </Sheet>
    </>
  );
}

export default function CostsPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense>
      <CostsScreen />
    </Suspense>
  );
}
