"use client";

/**
 * Casos, con el diseño de Rynx: indicadores arriba, filtros (estado y rango de
 * monto), la tabla y el detalle en un panel a la derecha.
 *
 * Los filtros viven en la dirección (?estado=...&q=...): se puede compartir el
 * link o volver atrás sin perderlos. `?caso=<id>` abre el detalle.
 */
import {
  CircleCheck,
  CircleDollarSign,
  Clock,
  Eye,
  FileText,
  Handshake,
  Landmark,
  PhoneCall,
  Phone,
  ShieldQuestion,
  UserRound,
  Users,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AmountRange } from "@/components/AmountRange";
import { CaseDetail } from "@/components/CaseDetail";
import { DataTable, type Column } from "@/components/DataTable";
import { Sheet } from "@/components/Sheet";
import { StatusBadge } from "@/components/StatusBadge";
import { KpiCard, PageHeader, QueryError, cx, inputClass } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  DEFAULT_CASE_FILTERS,
  CASE_STATUSES,
  readCaseFilters,
  useCases,
  useEscalateCase,
  useStartCall,
  type CaseFilters,
} from "@/features/cases";
import { useDashboard } from "@/features/dashboard";
import { formatMoney } from "@/lib/format";
import { CASE_STATUS_LABEL } from "@/lib/labels";
import { useDebounced } from "@/lib/useDebounced";
import type { CaseSort, CaseStatus, CaseSummary } from "@/lib/types";

function CasesScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readCaseFilters(params);
  const openCase = params.get("caso");
  const cases = useCases(filters);
  const me = useMe();
  const canOperate = can(me.data, "operate_portfolio");
  const [search, setSearch] = useState(filters.search);
  const typed = useDebounced(search);

  function update(changes: Partial<CaseFilters> & { caso?: string | null }) {
    const next = { ...filters, page: 1, ...changes };
    const query = new URLSearchParams();
    if (next.status) query.set("estado", next.status);
    if (next.search.trim()) query.set("q", next.search.trim());
    if (next.minAmount !== null) query.set("desde", String(next.minAmount));
    if (next.maxAmount !== null) query.set("hasta", String(next.maxAmount));
    if (next.sort !== DEFAULT_CASE_FILTERS.sort) query.set("orden", next.sort);
    if (next.page > 1) query.set("pagina", String(next.page));
    if (next.pageSize !== DEFAULT_CASE_FILTERS.pageSize) query.set("filas", String(next.pageSize));
    const caso = changes.caso === undefined ? openCase : changes.caso;
    if (caso) query.set("caso", caso);
    const text = query.toString();
    router.push(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }

  // El buscador pide al backend cuando la persona deja de escribir.
  useEffect(() => {
    if (typed.trim() !== filters.search.trim()) update({ search: typed });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando cambia lo escrito
  }, [typed]);

  const columns: Column<CaseSummary>[] = [
    {
      key: "number",
      header: "N° Caso",
      sortKey: "number",
      cell: (row) => <span className="tabular">#{row.number}</span>,
    },
    {
      key: "debtor",
      header: "Deudor",
      sortKey: "debtor",
      cell: (row) => <span className="font-bold">{row.debtor.name}</span>,
    },
    {
      key: "document",
      header: "DNI/CUIT/CUIL",
      sortKey: "document",
      className: "whitespace-nowrap",
      cell: (row) => row.debtor.document_number,
    },
    {
      key: "amount",
      header: "Monto",
      sortKey: "amount",
      className: "whitespace-nowrap tabular",
      cell: (row) => formatMoney(row.total_amount),
    },
    {
      key: "invoices",
      header: "Cant. Facturas",
      sortKey: "invoices",
      className: "tabular",
      cell: (row) => row.invoice_count,
    },
    {
      key: "status",
      header: "Estado",
      sortKey: "status",
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "actions",
      header: "Acciones",
      cell: (row) => (
        <RowActions
          row={row}
          canOperate={canOperate}
          onOpen={() => update({ caso: row.id, page: filters.page })}
        />
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Casos" subtitle="Visualización técnica de legajos y estados operativos." />

      <CaseKpis />

      <div className="mb-5 flex flex-wrap items-end gap-x-8 gap-y-4">
        <label className="block">
          <span className="text-xs font-bold text-ink">Todos los estados</span>
          <select
            value={filters.status}
            onChange={(event) => update({ status: event.target.value as CaseStatus | "" })}
            className={inputClass(false, "mt-2 w-48")}
          >
            <option value="">Todos los estados</option>
            {CASE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {CASE_STATUS_LABEL[status]}
              </option>
            ))}
          </select>
        </label>
        {cases.data && (
          <AmountRange
            max={Number(cases.data.amount_max)}
            value={{ min: filters.minAmount, max: filters.maxAmount }}
            onChange={(range) => update({ minAmount: range.min, maxAmount: range.max })}
          />
        )}
      </div>

      {cases.isError ? (
        <QueryError error={cases.error} retry={cases.refetch} />
      ) : (
        <DataTable
          caption="Casos"
          columns={columns}
          rows={cases.data?.items ?? []}
          rowKey={(row) => row.id}
          loading={cases.isFetching}
          search={{
            value: search,
            onChange: setSearch,
            placeholder: "Buscar por deudor, DNI o número de caso...",
          }}
          sort={filters.sort}
          onSort={(sort) => update({ sort: sort as CaseSort })}
          page={filters.page}
          pageSize={filters.pageSize}
          total={cases.data?.total}
          onPage={(page) => update({ page })}
          onPageSize={(pageSize) => update({ pageSize })}
          empty={
            filters.status || filters.search || filters.minAmount !== null || filters.maxAmount !== null
              ? "Ningún caso coincide con los filtros."
              : "Todavía no hay casos. Se arman desde Facturas, con “Generar casos”."
          }
        />
      )}

      <Sheet title="Detalle del caso" open={Boolean(openCase)} onClose={() => update({ caso: null, page: filters.page })}>
        {openCase && <CaseDetail caseId={openCase} />}
      </Sheet>
    </>
  );
}

// ---------------------------------------------------------------- indicadores

function CaseKpis() {
  const dashboard = useDashboard();
  if (!dashboard.data) return <div className="mb-6 h-24" aria-hidden />;
  const { portfolio: p, agent: a } = dashboard.data;
  const cases = (status: CaseStatus) => p.by_status.find((b) => b.key === status)?.cases ?? 0;

  return (
    <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      <KpiCard label="Total casos" value={p.cases_total} icon={<FileText />} hint="Todos los casos de la cartera, en cualquier estado." />
      <KpiCard label="Pendientes" value={cases("pending")} icon={<Clock />} hint="Todavía no se habló con el deudor." />
      <KpiCard label="Contactados" value={cases("contacted")} icon={<Phone />} hint="Se habló con el deudor, sin acuerdo todavía." />
      <KpiCard label="Compromisos de pago" value={cases("agreement")} icon={<Handshake />} hint="El deudor aceptó una oferta en la llamada." />
      <KpiCard label="Derivados a humanos" value={cases("escalated")} icon={<Users />} hint="Los tiene que atender una persona." />
      <KpiCard label="Desconocen las deudas" value={cases("disputed")} icon={<ShieldQuestion />} hint="El deudor dijo que no reconoce la deuda." />
      <KpiCard label="Cerrados" value={cases("closed")} icon={<CircleCheck />} hint="Casos terminados." />
      <KpiCard label="Deuda total" value={formatMoney(p.amount_total)} icon={<Landmark />} hint="La suma de todos los casos." />
      <KpiCard label="Deuda en gestión" value={formatMoney(p.in_progress_amount)} icon={<CircleDollarSign />} hint="Casos pendientes o contactados: los que el agente todavía puede negociar." />
      <KpiCard label="Llamadas" value={a.calls} icon={<PhoneCall />} hint="Llamadas del agente que ya terminaron." />
    </div>
  );
}

// ---------------------------------------------------------------- acciones de cada fila

function RowActions({
  row,
  canOperate,
  onOpen,
}: {
  row: CaseSummary;
  canOperate: boolean;
  onOpen: () => void;
}) {
  const call = useStartCall(row.id);
  const escalate = useEscalateCase(row.id);
  const negotiable = row.status === "pending" || row.status === "contacted";
  const error = call.error ?? escalate.error;

  return (
    <div className="flex items-center gap-2">
      <IconButton label={`Ver el caso #${row.number}`} onClick={onOpen} className="border-gray-300 bg-white text-ink hover:bg-sunken">
        <Eye className="size-4" />
      </IconButton>
      {canOperate && negotiable && (
        <>
          <IconButton
            label={call.isSuccess ? "Llamada iniciada" : `Llamar a ${row.debtor.name}`}
            onClick={() => call.mutate()}
            disabled={call.isPending || call.isSuccess}
            className="border-emerald-200 bg-emerald-50 text-emerald-600 hover:bg-emerald-100"
          >
            <Phone className="size-4" />
          </IconButton>
          <IconButton
            label={`Derivar el caso #${row.number} a una persona`}
            onClick={() => {
              if (window.confirm(`¿Derivar el caso #${row.number} a una persona? El agente deja de llamarlo.`)) {
                escalate.mutate();
              }
            }}
            disabled={escalate.isPending}
            className="border-red-200 bg-red-50 text-red-500 hover:bg-red-100"
          >
            <UserRound className="size-4" />
          </IconButton>
        </>
      )}
      {error && (
        <span role="alert" className="max-w-40 text-xs text-danger">
          {error instanceof Error ? error.message : "No se pudo."}
        </span>
      )}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  className,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  className: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      disabled={disabled}
      className={cx("flex size-9 items-center justify-center rounded-lg border disabled:opacity-50", className)}
    >
      <span aria-hidden>{children}</span>
    </button>
  );
}

export default function CasesPage() {
  return (
    <Suspense>
      <CasesScreen />
    </Suspense>
  );
}
