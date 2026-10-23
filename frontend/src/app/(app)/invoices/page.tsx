"use client";

/**
 * Facturas, con el diseño de Rynx: tres grupos según el vencimiento.
 *
 *   (🔔)──────────────(💬)──────────────(⚖)
 *  Grupo 1           Grupo 2           Grupo 3
 *  próximas a vencer vencen hoy        vencidas  → se agrupan en casos
 *
 * Cada grupo muestra su tabla con buscador, rango de monto, orden y páginas
 * (todo lo filtra el backend). En el grupo 3 está "Generar casos".
 *
 * Los filtros viven en la dirección (?grupo=vencidas&q=...): se puede volver
 * atrás o compartir el link sin perderlos.
 */
import { BellRing, CloudUpload, MessagesSquare, Scale } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AmountRange } from "@/components/AmountRange";
import { DataTable, type Column } from "@/components/DataTable";
import { GenerateCases } from "@/components/GenerateCases";
import { Stepper, type Step } from "@/components/Stepper";
import { PageHeader, QueryError, buttonClass, inputClass } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  DEFAULT_INVOICE_FILTERS,
  invoiceFiltersQuery,
  readInvoiceFilters,
  useInvoiceGroupCounts,
  useInvoices,
  type CaseFilter,
  type InvoiceFilters,
  type InvoiceGroup,
} from "@/features/invoices";
import { formatDate, formatMoney } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import type { Invoice, InvoiceSort } from "@/lib/types";


const EMPTY_TEXT: Record<InvoiceGroup, string> = {
  upcoming: "No hay facturas por vencer.",
  due_today: "Ninguna factura vence hoy.",
  overdue: "No hay facturas vencidas.",
};

function InvoicesScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const filters = readInvoiceFilters(useSearchParams());
  const invoices = useInvoices(filters);
  const counts = useInvoiceGroupCounts();
  const me = useMe();
  const canOperate = can(me.data, "operate_portfolio");
  const [search, setSearch] = useState(filters.search);
  const typed = useDebounced(search);

  function update(changes: Partial<InvoiceFilters>) {
    const text = invoiceFiltersQuery({ ...filters, page: 1, ...changes });
    router.push(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }

  // Cambiar de grupo empieza de cero: otro buscador, otro rango, primera página.
  function selectGroup(group: InvoiceGroup) {
    setSearch("");
    update({ ...DEFAULT_INVOICE_FILTERS, group, pageSize: filters.pageSize });
  }

  // El buscador pide al backend cuando la persona deja de escribir.
  useEffect(() => {
    if (typed.trim() !== filters.search.trim()) update({ search: typed });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando cambia lo escrito
  }, [typed]);

  const steps: Step<InvoiceGroup>[] = [
    { value: "upcoming", title: "Grupo 1", subtitle: "Facturas próximas a vencer", icon: BellRing, badge: counts.data?.upcoming },
    { value: "due_today", title: "Grupo 2", subtitle: "Facturas que vencen hoy", icon: MessagesSquare, badge: counts.data?.due_today },
    { value: "overdue", title: "Grupo 3", subtitle: "Facturas vencidas", icon: Scale, badge: counts.data?.overdue },
  ];

  const columns: Column<Invoice>[] = [
    {
      key: "external_id",
      header: "Número de factura",
      sortKey: "external_id",
      className: "whitespace-nowrap",
      cell: (row) => row.external_id,
    },
    { key: "description", header: "Concepto", sortKey: "description", cell: (row) => row.description },
    {
      key: "amount",
      header: "Monto",
      sortKey: "amount",
      className: "whitespace-nowrap tabular",
      cell: (row) => formatMoney(row.amount, row.currency),
    },
    {
      key: "due_date",
      header: "Fecha de vencimiento",
      sortKey: "due_date",
      className: "whitespace-nowrap tabular",
      cell: (row) => formatDate(row.due_date),
    },
    { key: "debtor", header: "Deudor", sortKey: "debtor", cell: (row) => row.debtor_name },
  ];
  if (filters.group === "overdue") {
    columns.push({
      key: "case",
      header: "Caso",
      className: "whitespace-nowrap",
      cell: (row) =>
        row.case_id ? (
          <Link href={`/cases?caso=${row.case_id}`} className="font-semibold text-rynx-primary hover:underline">
            #{row.case_number}
          </Link>
        ) : (
          <span className="text-muted">Sin caso</span>
        ),
    });
  }

  const filtered =
    filters.search.trim() !== "" ||
    filters.minAmount !== null ||
    filters.maxAmount !== null ||
    filters.inCase !== "all";

  return (
    <>
      <PageHeader
        title="Facturas"
        subtitle="Gestioná tus facturas por vencimiento y creá casos para que el agente negocie las vencidas."
        actions={
          canOperate && (
            <Link href="/invoices/upload" className={buttonClass("secondary")}>
              <CloudUpload aria-hidden className="size-4" /> Cargar facturas
            </Link>
          )
        }
      />

      <Stepper label="Grupos de facturas" steps={steps} current={filters.group} onSelect={selectGroup} />

      {filters.group === "overdue" && (
        <div className="mb-5">
          <GenerateCases canOperate={canOperate} />
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-end gap-x-8 gap-y-4">
        {filters.group === "overdue" && (
          <label className="block">
            <span className="text-xs font-bold text-ink">Casos</span>
            <select
              value={filters.inCase}
              onChange={(event) => update({ inCase: event.target.value as CaseFilter })}
              className={inputClass(false, "mt-2 w-48")}
            >
              <option value="all">Todas</option>
              <option value="unassigned">Sin caso</option>
              <option value="in_case">En un caso</option>
            </select>
          </label>
        )}
        {invoices.data && (
          <AmountRange
            max={Number(invoices.data.amount_max)}
            value={{ min: filters.minAmount, max: filters.maxAmount }}
            onChange={(range) => update({ minAmount: range.min, maxAmount: range.max })}
          />
        )}
      </div>

      {invoices.isError ? (
        <QueryError error={invoices.error} retry={invoices.refetch} />
      ) : (
        <DataTable
          caption={steps.find((s) => s.value === filters.group)?.subtitle ?? "Facturas"}
          columns={columns}
          rows={invoices.data?.items ?? []}
          rowKey={(row) => row.id}
          loading={invoices.isFetching}
          search={{
            value: search,
            onChange: setSearch,
            placeholder: "Buscar por número, concepto, deudor o DNI...",
          }}
          sort={filters.sort}
          onSort={(sort) => update({ sort: sort as InvoiceSort })}
          page={filters.page}
          pageSize={filters.pageSize}
          total={invoices.data?.total}
          onPage={(page) => update({ page })}
          onPageSize={(pageSize) => update({ pageSize })}
          empty={
            filtered ? (
              "Ninguna factura coincide con los filtros."
            ) : counts.data && counts.data.upcoming + counts.data.due_today + counts.data.overdue === 0 ? (
              canOperate ? (
                <>
                  Todavía no hay facturas.{" "}
                  <Link href="/invoices/upload" className="font-semibold text-rynx-primary underline">
                    Cargá la planilla
                  </Link>{" "}
                  para empezar.
                </>
              ) : (
                "Todavía no hay facturas. Las carga alguien con rol de operador o administración."
              )
            ) : (
              EMPTY_TEXT[filters.group]
            )
          }
        />
      )}
    </>
  );
}

export default function InvoicesPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense>
      <InvoicesScreen />
    </Suspense>
  );
}
