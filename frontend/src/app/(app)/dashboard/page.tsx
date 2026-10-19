"use client";

/**
 * Inicio: el tablero de la empresa. Todos los números vienen calculados de
 * GET /dashboard (ADR-029: nada inventado). Acá solo se dibujan.
 */
import Link from "next/link";

import { EmptyState, LoadingState, Panel, QueryError, cx } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { share, useDashboard } from "@/features/dashboard";
import { count, formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { AGE_BUCKET_LABEL, CALL_RESULT_LABEL, CASE_STATUS_HINT, CASE_STATUS_LABEL } from "@/lib/labels";
import type { CallResult, CaseStatus, Dashboard } from "@/lib/types";

// Orden de la barra por estado. Verde y rojo NO van pegados: con daltonismo
// rojo-verde se confunden (validado con la guía de gráficos: ver ADR-033).
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

// ---------------------------------------------------------------- piezas

function StatTile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-5 py-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight [font-variant-numeric:normal]">{value}</p>
      {detail && <p className="mt-0.5 text-sm text-muted">{detail}</p>}
    </div>
  );
}

/** Deuda en gestión por antigüedad: barras horizontales de un solo color (es magnitud). */
function AgeBars({ data }: { data: Dashboard["portfolio"] }) {
  const max = data.in_progress_by_age.reduce(
    (top, b) => (Number(b.amount) > Number(top) ? b.amount : top),
    "0",
  );
  return (
    <ul className="space-y-4">
      {data.in_progress_by_age.map((bucket) => {
        const width = share(bucket.amount, max);
        const label = `${AGE_BUCKET_LABEL[bucket.key]}: ${formatMoney(bucket.amount)} en ${count(bucket.cases, "caso", "casos")}`;
        return (
          <li key={bucket.key} title={label} aria-label={label}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span>{AGE_BUCKET_LABEL[bucket.key]}</span>
              <span className="text-muted">{count(bucket.cases, "caso", "casos")}</span>
            </div>
            <div className="mt-1.5 flex items-center gap-3">
              <div className="h-5 flex-1">
                {width > 0 && (
                  <div
                    aria-hidden
                    className="h-full rounded-r bg-petrol"
                    style={{ width: `${Math.max(width * 100, 1)}%` }}
                  />
                )}
              </div>
              <span className="w-32 shrink-0 text-right text-sm font-semibold tabular-nums">
                {formatMoney(bucket.amount)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Cartera por estado: barra apilada (parte del total) + leyenda que también es tabla. */
function StatusStack({ data }: { data: Dashboard["portfolio"] }) {
  const byKey = new Map(data.by_status.map((b) => [b.key, b]));
  const rows = STATUS_ORDER.map((status) => byKey.get(status)!).filter(Boolean);
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
                  <span aria-hidden className={cx("size-2.5 shrink-0 rounded-sm", STATUS_FILL[bucket.key])} />
                  {CASE_STATUS_LABEL[bucket.key]}
                </span>
              </th>
              <td className="py-1.5 pr-3 text-right tabular-nums">{bucket.cases}</td>
              <td className="py-1.5 text-right font-medium tabular-nums">{formatMoney(bucket.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line">
            <th scope="row" className="pt-2 pr-3 text-left font-semibold">
              Total
            </th>
            <td className="pt-2 pr-3 text-right font-semibold tabular-nums">{data.cases_total}</td>
            <td className="pt-2 text-right font-semibold tabular-nums">{formatMoney(data.amount_total)}</td>
          </tr>
        </tfoot>
      </table>
    </>
  );
}

function AgentPanel({ data }: { data: Dashboard["agent"] }) {
  if (data.calls === 0) {
    return (
      <p className="text-sm text-muted">
        Todavía no hubo llamadas. Cuando el agente llame, acá vas a ver cómo terminaron.
      </p>
    );
  }
  const results: { label: string; value: number }[] = [
    ...RESULT_ORDER.map((r) => ({ label: CALL_RESULT_LABEL[r], value: data.calls_by_result[r] })),
    { label: "Cortó antes de un resultado", value: data.calls_without_result },
  ];
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-4">
        <div>
          <dt className="text-sm text-muted">Llamadas</dt>
          <dd className="text-2xl font-bold">{data.calls}</dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Identidad verificada</dt>
          <dd className="text-2xl font-bold">
            {data.identity_verified}
            <span className="text-base font-normal text-muted"> de {data.calls}</span>
          </dd>
        </div>
      </dl>
      <table className="w-full text-sm">
        <caption className="sr-only">Cómo terminaron las llamadas</caption>
        <tbody>
          {results.map(({ label, value }) => (
            <tr key={label} className={cx("border-t border-line", value === 0 && "text-muted")}>
              <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                {label}
              </th>
              <td className="py-1.5 text-right tabular-nums">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.last_call_at && (
        <p className="text-xs text-muted">Última llamada: {formatDateTime(data.last_call_at)}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- pantalla

function DashboardView({ data, canOperate }: { data: Dashboard; canOperate: boolean }) {
  const { portfolio: p, agent: a } = data;

  if (p.cases_total === 0 && p.unassigned_overdue_invoices === 0 && p.upcoming_invoices === 0) {
    return (
      <EmptyState title="Todavía no hay datos para mostrar">
        {canOperate ? (
          <>
            Empezá por{" "}
            <Link href="/invoices/upload" className="text-petrol underline">
              cargar las facturas
            </Link>{" "}
            y generar los casos.
          </>
        ) : (
          "Aparecen cuando alguien de operación o administración carga las facturas."
        )}
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="hero" className="rounded-lg border border-petrol/25 bg-petrol-soft px-6 py-6">
        <p id="hero" className="text-sm text-muted">
          Deuda en gestión
        </p>
        <p className="mt-1 text-4xl font-bold tracking-tight [overflow-wrap:anywhere] [font-variant-numeric:normal] sm:text-5xl">
          {formatMoney(p.in_progress_amount)}
        </p>
        <p className="mt-2 max-w-xl text-sm text-muted">
          {count(p.in_progress_cases, "caso pendiente o contactado", "casos pendientes o contactados")}: los
          que el agente todavía puede negociar.
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          label="Acuerdos de pago"
          value={formatMoney(a.agreed_amount)}
          detail={
            a.agreements === 0
              ? "Todavía ninguno"
              : `${count(a.agreements, "acuerdo", "acuerdos")} (${a.agreements_single_payment} de pago único, ${a.agreements_installments} en cuotas) sobre ${formatMoney(a.agreed_original_amount)} de deuda`
          }
        />
        <StatTile
          label="Vencidas sin caso"
          value={formatMoney(p.unassigned_overdue_amount)}
          detail={count(p.unassigned_overdue_invoices, "factura", "facturas")}
        />
        <StatTile
          label="Por vencer"
          value={formatMoney(p.upcoming_amount)}
          detail={count(p.upcoming_invoices, "factura", "facturas")}
        />
      </div>

      {p.unassigned_overdue_invoices > 0 && canOperate && (
        <p className="text-sm">
          Hay facturas vencidas que todavía no están en un caso.{" "}
          <Link href="/invoices?filter=unassigned" className="text-petrol underline">
            Revisarlas y generar los casos
          </Link>
        </p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Panel title="Deuda en gestión por antigüedad">
          <AgeBars data={p} />
          <p className="mt-4 text-xs text-muted">Días de atraso al {formatDate(data.as_of)}.</p>
        </Panel>
        <Panel title="Cartera por estado">
          <StatusStack data={p} />
        </Panel>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Panel title="Llamadas del agente">
          <AgentPanel data={a} />
        </Panel>
        <Panel title="Qué cuentan estos números">
          <ul className="space-y-2 text-sm text-muted">
            <li>
              <span className="font-medium text-ink">Acuerdos de pago</span> es lo que los deudores se
              comprometieron a pagar en la llamada. Todavía no es plata cobrada: Mavic no registra pagos.
            </li>
            <li>
              <span className="font-medium text-ink">Deuda en gestión</span> suma los casos pendientes y
              contactados. Los que tienen acuerdo, disputa o derivación ya no se negocian.
            </li>
            <li>Todo se calcula con los datos de tu empresa en el momento en que abrís esta pantalla.</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const me = useMe();
  const dashboard = useDashboard();

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Inicio</h1>
      <div className="mt-6">
        {dashboard.isPending && <LoadingState label="Calculando los números…" />}
        {dashboard.isError && <QueryError error={dashboard.error} retry={dashboard.refetch} />}
        {dashboard.isSuccess && (
          <DashboardView data={dashboard.data} canOperate={can(me.data, "operate_portfolio")} />
        )}
      </div>
    </>
  );
}
