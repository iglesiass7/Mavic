"use client";

import { ChevronLeft, ChevronRight, Upload } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { GenerateCases } from "@/components/GenerateCases";
import { Button, EmptyState, LoadingState, QueryError, buttonClass, cx } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { INVOICES_PAGE_SIZE, useInvoices, type InvoiceFilter } from "@/features/invoices";
import { formatDate, formatMoney } from "@/lib/format";
import { INVOICE_STAGE_LABEL } from "@/lib/labels";
import type { InvoiceStage } from "@/lib/types";

const FILTERS: { value: InvoiceFilter; label: string }[] = [
  { value: "all", label: "Todas" },
  { value: "unassigned", label: "Vencidas sin caso" },
  { value: "in_case", label: "En un caso" },
];

const EMPTY_TEXT: Record<InvoiceFilter, string> = {
  all: "",
  unassigned: "Todas las facturas vencidas ya están en un caso.",
  in_case: "Ninguna factura está en un caso todavía.",
};

const STAGE_COLOR: Record<InvoiceStage, string> = {
  upcoming: "text-muted",
  due_today: "text-status-pending",
  overdue: "text-status-disputed",
};

/** Lee los filtros de la URL, ignorando valores inventados. */
function readFilters(params: URLSearchParams): { filter: InvoiceFilter; page: number } {
  const filter = params.get("filter") as InvoiceFilter;
  const page = Number(params.get("page"));
  return {
    filter: FILTERS.some((f) => f.value === filter) ? filter : "all",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

function InvoicesList() {
  const router = useRouter();
  const pathname = usePathname();
  const { filter, page } = readFilters(useSearchParams());
  const me = useMe();
  const canOperate = can(me.data, "operate_portfolio");
  const invoices = useInvoices(filter, page);

  function go(next: { filter?: InvoiceFilter; page?: number }) {
    const params = new URLSearchParams();
    const nextFilter = next.filter ?? filter;
    const nextPage = next.page ?? 1;
    if (nextFilter !== "all") params.set("filter", nextFilter);
    if (nextPage > 1) params.set("page", String(nextPage));
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  const total = invoices.data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / INVOICES_PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * INVOICES_PAGE_SIZE + 1;
  const to = Math.min(page * INVOICES_PAGE_SIZE, total);

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Facturas</h1>
          <p className="mt-1 text-sm text-muted">
            Las facturas cargadas. Las vencidas se agrupan en casos, uno por deudor.
          </p>
        </div>
        {canOperate && (
          <Link href="/invoices/upload" className={buttonClass("secondary")}>
            <Upload aria-hidden className="size-4" /> Cargar facturas
          </Link>
        )}
      </div>

      <div className="mt-6 space-y-5">
        <GenerateCases canOperate={canOperate} />

        <div role="group" aria-label="Qué facturas mostrar" className="flex flex-wrap gap-1">
          {FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => go({ filter: value })}
              className={cx(
                "rounded-md px-3 py-1.5 text-sm",
                filter === value
                  ? "bg-ink font-semibold text-white"
                  : "text-muted hover:bg-surface hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {invoices.isPending && <LoadingState label="Cargando facturas…" />}
        {invoices.isError && <QueryError error={invoices.error} retry={invoices.refetch} />}

        {invoices.isSuccess && total === 0 && (
          <EmptyState title={filter === "all" ? "Todavía no hay facturas" : "No hay facturas acá"}>
            {filter !== "all" ? (
              EMPTY_TEXT[filter]
            ) : canOperate ? (
              <>
                Empezá por{" "}
                <Link href="/invoices/upload" className="text-petrol underline">
                  cargar el archivo de facturas
                </Link>
                .
              </>
            ) : (
              "Las carga alguien con rol de operador o administración."
            )}
          </EmptyState>
        )}

        {invoices.isSuccess && total > 0 && (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-sm">
              <caption className="sr-only">Facturas cargadas</caption>
              <thead className="border-b border-line text-left text-xs text-muted">
                <tr>
                  <th scope="col" className="hidden px-4 py-3 font-medium md:table-cell">Factura</th>
                  <th scope="col" className="px-4 py-3 font-medium">Deudor</th>
                  <th scope="col" className="hidden px-4 py-3 font-medium lg:table-cell">Concepto</th>
                  <th scope="col" className="hidden px-4 py-3 font-medium sm:table-cell">Vencimiento</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Monto</th>
                  <th scope="col" className="hidden px-4 py-3 font-medium sm:table-cell">Caso</th>
                </tr>
              </thead>
              <tbody className={invoices.isPlaceholderData ? "opacity-60" : undefined}>
                {invoices.data.items.map((invoice) => (
                  <tr key={invoice.id} className="border-b border-line last:border-0">
                    <td className="hidden px-4 py-3 whitespace-nowrap text-muted md:table-cell">
                      {invoice.external_id}
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium">{invoice.debtor_name}</span>
                      {/* En pantallas chicas, el concepto va debajo del nombre. */}
                      <span className="block text-xs text-muted lg:hidden">{invoice.description}</span>
                      {invoice.case_id && (
                        <Link
                          href={`/cases/${invoice.case_id}`}
                          className="block text-xs text-petrol hover:underline sm:hidden"
                        >
                          Caso {invoice.case_number}
                        </Link>
                      )}
                    </td>
                    <td className="hidden px-4 py-3 lg:table-cell">{invoice.description}</td>
                    <td className="hidden px-4 py-3 whitespace-nowrap sm:table-cell">
                      {formatDate(invoice.due_date)}
                      <span className={cx("block text-xs", STAGE_COLOR[invoice.stage])}>
                        {INVOICE_STAGE_LABEL[invoice.stage]}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <span className="font-semibold">{formatMoney(invoice.amount, invoice.currency)}</span>
                      {/* En el celular, el vencimiento va debajo del monto. */}
                      <span className={cx("block text-xs sm:hidden", STAGE_COLOR[invoice.stage])}>
                        {INVOICE_STAGE_LABEL[invoice.stage]} · {formatDate(invoice.due_date)}
                      </span>
                    </td>
                    <td className="hidden px-4 py-3 whitespace-nowrap sm:table-cell">
                      {invoice.case_id ? (
                        <Link href={`/cases/${invoice.case_id}`} className="text-petrol hover:underline">
                          Caso {invoice.case_number}
                        </Link>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {invoices.isSuccess && total > INVOICES_PAGE_SIZE && (
          <nav aria-label="Páginas" className="flex items-center justify-between text-sm">
            <span className="text-muted">
              {from}–{to} de {total}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>
                <ChevronLeft aria-hidden className="size-4" /> Anterior
              </Button>
              <Button
                variant="secondary"
                disabled={page >= lastPage}
                onClick={() => go({ page: page + 1 })}
              >
                Siguiente <ChevronRight aria-hidden className="size-4" />
              </Button>
            </div>
          </nav>
        )}
      </div>
    </>
  );
}

export default function InvoicesPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense fallback={<LoadingState />}>
      <InvoicesList />
    </Suspense>
  );
}
