"use client";

/**
 * Dashboard, con el diseño de Rynx: pestañas General / Casos / Contactabilidad,
 * indicadores arriba y gráficos abajo.
 *
 * Todos los números vienen calculados de GET /dashboard (ADR-033): acá solo se
 * dibujan. Rynx tenía números escritos en el código y comparaciones "vs mes
 * anterior"; Mavic todavía no guarda historia, así que solo muestra lo de hoy.
 *
 * Gráficos (guía de visualización):
 *   - cantidades por categoría -> barras de UN color (es magnitud, no identidad)
 *   - estados del caso         -> el color de cada estado (el mismo de la etiqueta)
 *   - cada barra tiene su valor escrito, y al pasar el mouse o con el teclado, el detalle
 */
import {
  CircleDollarSign,
  Clock,
  FileText,
  Handshake,
  Landmark,
  Phone,
  PhoneCall,
  PhoneMissed,
  Percent,
  Timer,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { Card, EmptyState, KpiCard, LoadingState, PageHeader, QueryError, Tabs, cx } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { share, useDashboard } from "@/features/dashboard";
import { count, formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { AGE_BUCKET_LABEL, CALL_RESULT_LABEL, CASE_STATUS_HINT, CASE_STATUS_LABEL } from "@/lib/labels";
import type { CallResult, CaseStatus, Dashboard } from "@/lib/types";

type Tab = "general" | "cases" | "calls";

// Orden de los estados: verde y rojo no van pegados (con daltonismo rojo-verde
// se confunden). Validado con el script de la guía de gráficos (ADR-033).
const STATUS_ORDER: CaseStatus[] = ["agreement", "contacted", "pending", "escalated", "disputed", "closed"];
const STATUS_FILL: Record<CaseStatus, string> = {
  agreement: "bg-status-agreement",
  contacted: "bg-status-contacted",
  pending: "bg-status-pending",
  escalated: "bg-status-escalated",
  disputed: "bg-status-disputed",
  closed: "bg-status-closed",
};
const RESULT_ORDER: CallResult[] = ["ACUERDO", "CONTACTADO", "DERIVACION_HUMANA", "DESCONOCIMIENTO"];

function percent(part: number, total: number): string {
  if (total <= 0) return "0 %";
  return `${Math.round((part / total) * 100)} %`;
}

// ---------------------------------------------------------------- piezas de gráfico

/** Una tarjeta de gráfico de Rynx: título a la izquierda, contenido abajo. */
function ChartCard({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
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
function Tip({ text, children, className }: { text: string; children: ReactNode; className?: string }) {
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

interface BarRow {
  key: string;
  label: string;
  value: number;
  valueText: string;
  tip: string;
  fill?: string; // clase de color; por defecto el verde de la marca
}

/** Barras horizontales: nombre a la izquierda, barra, valor a la derecha. */
function BarList({ rows, caption }: { rows: BarRow[]; caption: string }) {
  const max = Math.max(...rows.map((r) => r.value), 0);
  return (
    <>
      <ul className="space-y-3" aria-hidden>
        {rows.map((row) => (
          <li key={row.key} className="grid grid-cols-[minmax(7rem,10rem)_1fr_auto] items-center gap-3 text-sm">
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

/** Columnas verticales (antigüedad de la deuda): una barra por tramo. */
function ColumnChart({ rows, caption }: { rows: BarRow[]; caption: string }) {
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

/** Embudo de conversión: cada etapa con su ancho relativo a la primera. */
function Funnel({ stages }: { stages: { key: string; label: string; value: number; hint: string }[] }) {
  const first = stages[0]?.value ?? 0;
  return (
    <ol className="space-y-3">
      {stages.map((stage, index) => {
        const width = first > 0 ? Math.max((stage.value / first) * 100, stage.value > 0 ? 4 : 0) : 0;
        return (
          <li key={stage.key}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
              <span className="font-bold text-ink uppercase">{stage.label}</span>
              <span className="text-muted tabular">
                {stage.value}
                {index > 0 && ` · ${percent(stage.value, first)}`}
              </span>
            </div>
            <Tip text={stage.hint} className="h-7">
              <div className="mx-auto h-full rounded bg-rynx-primary" style={{ width: `${width}%`, opacity: 1 - index * 0.22 }} />
            </Tip>
          </li>
        );
      })}
    </ol>
  );
}

/** Cartera por estado: barra apilada (parte del total) + leyenda que también es tabla. */
function StatusStack({ data }: { data: Dashboard["portfolio"] }) {
  const byKey = new Map(data.by_status.map((b) => [b.key, b]));
  const rows = STATUS_ORDER.map((status) => byKey.get(status)).filter((b) => b !== undefined);
  const visible = rows.filter((b) => share(b.amount, data.amount_total) > 0);

  return (
    <>
      {/* gap-0.5 = 2px de separación en el color del fondo entre tramos */}
      <div aria-hidden className="flex h-6 gap-0.5 overflow-hidden rounded">
        {visible.map((bucket) => (
          <div
            key={bucket.key}
            title={`${CASE_STATUS_LABEL[bucket.key]}: ${formatMoney(bucket.amount)}`}
            className={STATUS_FILL[bucket.key]}
            style={{ flexGrow: share(bucket.amount, data.amount_total), flexBasis: 0, minWidth: 4 }}
          />
        ))}
      </div>
      <table className="mt-4 w-full text-sm">
        <caption className="sr-only">Casos y deuda por estado</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Estado</th>
            <th scope="col">Casos</th>
            <th scope="col">Deuda</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((bucket) => (
            <tr key={bucket.key} className={cx(bucket.cases === 0 && "text-muted")}>
              <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                <span className="inline-flex items-center gap-2" title={CASE_STATUS_HINT[bucket.key]}>
                  <span aria-hidden className={cx("size-2.5 shrink-0 rounded-full", STATUS_FILL[bucket.key])} />
                  {CASE_STATUS_LABEL[bucket.key]}
                </span>
              </th>
              <td className="py-1.5 pr-3 text-right tabular">{bucket.cases}</td>
              <td className="py-1.5 text-right font-medium tabular">{formatMoney(bucket.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line">
            <th scope="row" className="pt-2 pr-3 text-left font-bold">
              Total
            </th>
            <td className="pt-2 pr-3 text-right font-bold tabular">{data.cases_total}</td>
            <td className="pt-2 text-right font-bold tabular">{formatMoney(data.amount_total)}</td>
          </tr>
        </tfoot>
      </table>
    </>
  );
}

// ---------------------------------------------------------------- pestañas

function casesIn(data: Dashboard, status: CaseStatus): number {
  return data.portfolio.by_status.find((b) => b.key === status)?.cases ?? 0;
}

function GeneralTab({ data, canOperate }: { data: Dashboard; canOperate: boolean }) {
  const { portfolio: p, agent: a } = data;
  const reached = p.cases_total - casesIn(data, "pending") - casesIn(data, "closed");

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Deuda total"
          value={formatMoney(p.amount_total)}
          icon={<Landmark />}
          detail={count(p.cases_total, "caso", "casos")}
          hint="La suma de todos los casos, en cualquier estado."
        />
        <KpiCard
          label="Deuda en gestión"
          value={formatMoney(p.in_progress_amount)}
          icon={<CircleDollarSign />}
          detail={count(p.in_progress_cases, "caso pendiente o contactado", "casos pendientes o contactados")}
          hint="Lo que el agente todavía puede negociar: casos pendientes y contactados."
        />
        <KpiCard
          label="Acuerdos de pago"
          value={formatMoney(a.agreed_amount)}
          icon={<Handshake />}
          detail={a.agreements === 0 ? "Todavía ninguno" : count(a.agreements, "acuerdo", "acuerdos")}
          hint="Lo que los deudores se comprometieron a pagar en la llamada. No es plata cobrada todavía."
        />
        <KpiCard
          label="Por vencer"
          value={formatMoney(p.upcoming_amount)}
          icon={<Timer />}
          detail={count(p.upcoming_invoices, "factura", "facturas")}
          hint="Facturas que todavía no vencieron: no están en ningún caso."
        />
      </div>

      {p.unassigned_overdue_invoices > 0 && canOperate && (
        <p className="rounded-2xl border border-petrol/25 bg-petrol-soft px-5 py-3 text-sm">
          Hay {count(p.unassigned_overdue_invoices, "factura vencida", "facturas vencidas")} (
          {formatMoney(p.unassigned_overdue_amount)}) que todavía no están en un caso.{" "}
          <Link href="/invoices?grupo=vencidas&casos=sin-caso" className="font-semibold text-rynx-primary underline">
            Revisarlas y generar los casos
          </Link>
        </p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <ChartCard title="Cartera por estado">
          <StatusStack data={p} />
        </ChartCard>
        <ChartCard
          title="Conversión"
          footer="Contactados: casos en los que el agente ya habló con el deudor (contactado, acuerdo, disputa o derivado)."
        >
          <Funnel
            stages={[
              { key: "cases", label: "Casos", value: p.cases_total, hint: count(p.cases_total, "caso", "casos") },
              { key: "reached", label: "Contactados", value: reached, hint: `${reached} de ${p.cases_total} casos` },
              {
                key: "agreement",
                label: "Acuerdos",
                value: casesIn(data, "agreement"),
                hint: `${casesIn(data, "agreement")} de ${p.cases_total} casos`,
              },
            ]}
          />
        </ChartCard>
      </div>

      <ChartCard title="Tipo de acuerdo" footer={a.agreements === 0 ? "Todavía no hay acuerdos." : undefined}>
        <BarList
          caption="Acuerdos por tipo"
          rows={[
            {
              key: "single",
              label: "Pago único",
              value: a.agreements_single_payment,
              valueText: String(a.agreements_single_payment),
              tip: `Pago único: ${count(a.agreements_single_payment, "acuerdo", "acuerdos")}`,
            },
            {
              key: "installments",
              label: "En cuotas",
              value: a.agreements_installments,
              valueText: String(a.agreements_installments),
              tip: `En cuotas: ${count(a.agreements_installments, "acuerdo", "acuerdos")}`,
            },
          ]}
        />
      </ChartCard>
    </div>
  );
}

function CasesTab({ data }: { data: Dashboard }) {
  const { portfolio: p } = data;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <KpiCard label="Casos totales" value={p.cases_total} icon={<FileText />} hint="Todos los casos, en cualquier estado." />
        <KpiCard label="Pendientes" value={casesIn(data, "pending")} icon={<Clock />} hint={CASE_STATUS_HINT.pending} />
        <KpiCard label="Contactados" value={casesIn(data, "contacted")} icon={<Phone />} hint={CASE_STATUS_HINT.contacted} />
        <KpiCard label="Compromisos de pago" value={casesIn(data, "agreement")} icon={<Handshake />} hint={CASE_STATUS_HINT.agreement} />
        <KpiCard label="Derivados a humanos" value={casesIn(data, "escalated")} icon={<Users />} hint={CASE_STATUS_HINT.escalated} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <ChartCard title="Antigüedad de la deuda en gestión" footer={`Días de atraso al ${formatDate(data.as_of)}. Casos pendientes y contactados.`}>
          <ColumnChart
            caption="Casos en gestión por antigüedad de la deuda"
            rows={p.in_progress_by_age.map((bucket) => ({
              key: bucket.key,
              label: AGE_BUCKET_LABEL[bucket.key],
              value: bucket.cases,
              valueText: String(bucket.cases),
              tip: `${count(bucket.cases, "caso", "casos")}: ${formatMoney(bucket.amount)}`,
            }))}
          />
        </ChartCard>
        <ChartCard title="Casos por estado">
          <BarList
            caption="Casos por estado"
            rows={STATUS_ORDER.map((status) => {
              const bucket = p.by_status.find((b) => b.key === status);
              return {
                key: status,
                label: CASE_STATUS_LABEL[status],
                value: bucket?.cases ?? 0,
                valueText: String(bucket?.cases ?? 0),
                tip: `${count(bucket?.cases ?? 0, "caso", "casos")}: ${formatMoney(bucket?.amount ?? "0")}`,
                fill: STATUS_FILL[status],
              };
            })}
          />
        </ChartCard>
      </div>
    </div>
  );
}

function CallsTab({ data }: { data: Dashboard }) {
  const { agent: a } = data;
  const withResult = a.calls - a.calls_without_result;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <KpiCard label="Llamadas" value={a.calls} icon={<PhoneCall />} hint="Llamadas del agente que ya terminaron." />
        <KpiCard label="Con resultado" value={withResult} icon={<Phone />} hint="Llamadas que terminaron con un resultado registrado." />
        <KpiCard label="Sin resultado" value={a.calls_without_result} icon={<PhoneMissed />} hint="La llamada se cortó antes de llegar a un resultado." />
        <KpiCard label="Acuerdos" value={a.calls_by_result.ACUERDO} icon={<Handshake />} hint="Llamadas que terminaron en un compromiso de pago." />
        <KpiCard
          label="Tasa de acuerdo"
          value={percent(a.calls_by_result.ACUERDO, a.calls)}
          icon={<Percent />}
          hint="Acuerdos sobre el total de llamadas terminadas."
        />
      </div>

      <ChartCard
        title="Cómo terminaron las llamadas"
        footer={a.last_call_at ? `Última llamada: ${formatDateTime(a.last_call_at)}` : "Todavía no hubo llamadas."}
      >
        <BarList
          caption="Llamadas por resultado"
          rows={[
            ...RESULT_ORDER.map((result) => ({
              key: result,
              label: CALL_RESULT_LABEL[result],
              value: a.calls_by_result[result],
              valueText: String(a.calls_by_result[result]),
              tip: `${CALL_RESULT_LABEL[result]}: ${count(a.calls_by_result[result], "llamada", "llamadas")} (${percent(a.calls_by_result[result], a.calls)})`,
            })),
            {
              key: "none",
              label: "Cortó antes de un resultado",
              value: a.calls_without_result,
              valueText: String(a.calls_without_result),
              tip: `Sin resultado: ${count(a.calls_without_result, "llamada", "llamadas")}`,
            },
          ]}
        />
      </ChartCard>
    </div>
  );
}

// ---------------------------------------------------------------- pantalla

const TABS: { value: Tab; label: string }[] = [
  { value: "general", label: "General" },
  { value: "cases", label: "Casos" },
  { value: "calls", label: "Contactabilidad" },
];

export default function DashboardPage() {
  const me = useMe();
  const dashboard = useDashboard();
  const [tab, setTab] = useState<Tab>("general");
  const canOperate = can(me.data, "operate_portfolio");
  const data = dashboard.data;
  const empty =
    data &&
    data.portfolio.cases_total === 0 &&
    data.portfolio.unassigned_overdue_invoices === 0 &&
    data.portfolio.upcoming_invoices === 0;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Monitoreo de la cartera y de las llamadas del agente." />
      {dashboard.isPending && <LoadingState label="Calculando los números…" />}
      {dashboard.isError && <QueryError error={dashboard.error} retry={dashboard.refetch} />}
      {empty && (
        <EmptyState title="Todavía no hay datos para mostrar">
          {canOperate ? (
            <>
              Empezá por{" "}
              <Link href="/invoices/upload" className="font-semibold text-rynx-primary underline">
                cargar las facturas
              </Link>{" "}
              y generar los casos.
            </>
          ) : (
            "Aparecen cuando alguien de operación o administración carga las facturas."
          )}
        </EmptyState>
      )}
      {data && !empty && (
        <>
          <div className="mb-6">
            <Tabs label="Vistas del tablero" tabs={TABS} value={tab} onChange={setTab} />
          </div>
          {tab === "general" && <GeneralTab data={data} canOperate={canOperate} />}
          {tab === "cases" && <CasesTab data={data} />}
          {tab === "calls" && <CallsTab data={data} />}
        </>
      )}
    </>
  );
}
