"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button, EmptyState, LoadingState, QueryError } from "@/components/ui";
import { PAGE_SIZE, useCases, type CaseFilters } from "@/features/cases";
import { formatDays, formatMoney } from "@/lib/format";
import { CASE_SORT_LABEL, CASE_STATUS_LABEL } from "@/lib/labels";
import type { CaseSort, CaseStatus } from "@/lib/types";

const STATUSES = Object.keys(CASE_STATUS_LABEL) as CaseStatus[];
const SORTS = Object.keys(CASE_SORT_LABEL) as CaseSort[];

/** Lee los filtros de la URL, ignorando valores inventados (?status=cualquiera). */
function readFilters(params: URLSearchParams): CaseFilters {
  const status = params.get("status") as CaseStatus;
  const sort = params.get("sort") as CaseSort;
  const page = Number(params.get("page"));
  return {
    status: STATUSES.includes(status) ? status : "",
    sort: SORTS.includes(sort) ? sort : "oldest_debt",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

function CasesList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filters = readFilters(searchParams);
  const cases = useCases(filters);

  function update(changes: Partial<CaseFilters>) {
    const next = { ...filters, page: 1, ...changes };
    const params = new URLSearchParams();
    if (next.status) params.set("status", next.status);
    if (next.sort !== "oldest_debt") params.set("sort", next.sort);
    if (next.page > 1) params.set("page", String(next.page));
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  const total = cases.data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (filters.page - 1) * PAGE_SIZE + 1;
  const to = Math.min(filters.page * PAGE_SIZE, total);

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Casos</h1>
          <p className="mt-1 text-sm text-muted">
            Cada caso agrupa las facturas vencidas de un deudor.
          </p>
        </div>
        <div className="grid w-full grid-cols-2 gap-3 sm:flex sm:w-auto">
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">Estado</span>
            <select
              value={filters.status}
              onChange={(e) => update({ status: e.target.value as CaseStatus | "" })}
              className="w-full rounded-md border border-line bg-surface px-3 py-2"
            >
              <option value="">Todos</option>
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {CASE_STATUS_LABEL[status]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">Orden</span>
            <select
              value={filters.sort}
              onChange={(e) => update({ sort: e.target.value as CaseSort })}
              className="w-full rounded-md border border-line bg-surface px-3 py-2"
            >
              {SORTS.map((sort) => (
                <option key={sort} value={sort}>
                  {CASE_SORT_LABEL[sort]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="mt-6">
        {cases.isPending && <LoadingState label="Cargando casos…" />}
        {cases.isError && (
          <QueryError error={cases.error} retry={cases.refetch} />
        )}
        {cases.isSuccess && total === 0 && (
          <EmptyState
            title={filters.status ? `No hay casos "${CASE_STATUS_LABEL[filters.status]}"` : "Todavía no hay casos"}
          >
            {filters.status ? (
              "Probá con otro estado."
            ) : (
              <>
                Los casos se arman con las facturas vencidas: primero se{" "}
                <Link href="/invoices/upload" className="text-petrol underline">
                  cargan las facturas
                </Link>{" "}
                y después se generan los casos.
              </>
            )}
          </EmptyState>
        )}

        {cases.isSuccess && total > 0 && (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-sm">
              <caption className="sr-only">Casos de la cartera</caption>
              <thead className="border-b border-line text-left text-xs text-muted">
                <tr>
                  <th scope="col" className="hidden px-4 py-3 font-medium sm:table-cell">Caso</th>
                  <th scope="col" className="px-4 py-3 font-medium">Deudor</th>
                  <th scope="col" className="px-4 py-3 font-medium">Estado</th>
                  <th scope="col" className="hidden px-4 py-3 text-right font-medium md:table-cell">Facturas</th>
                  <th scope="col" className="hidden px-4 py-3 text-right font-medium sm:table-cell">Atraso</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Deuda</th>
                </tr>
              </thead>
              <tbody className={cases.isPlaceholderData ? "opacity-60" : undefined}>
                {cases.data.items.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => router.push(`/cases/${item.id}`)}
                    className="cursor-pointer border-b border-line last:border-0 hover:bg-paper"
                  >
                    <td className="hidden px-4 py-3 text-muted sm:table-cell">{item.number}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/cases/${item.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-semibold hover:text-petrol"
                      >
                        {item.debtor.name}
                      </Link>
                      <span className="block text-xs whitespace-nowrap text-muted">
                        DNI {item.debtor.document_number}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="hidden px-4 py-3 text-right md:table-cell">{item.invoice_count}</td>
                    <td className="hidden px-4 py-3 text-right whitespace-nowrap sm:table-cell">
                      {formatDays(item.debt_age_days)}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <span className="font-semibold">{formatMoney(item.total_amount)}</span>
                      {/* En celular no entra la columna "Atraso": va debajo del monto. */}
                      <span className="block text-xs text-muted sm:hidden">
                        {formatDays(item.debt_age_days)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {cases.isSuccess && total > PAGE_SIZE && (
          <nav aria-label="Páginas" className="mt-4 flex items-center justify-between text-sm">
            <span className="text-muted">
              {from}–{to} de {total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={filters.page <= 1}
                onClick={() => update({ page: filters.page - 1 })}
              >
                <ChevronLeft aria-hidden className="size-4" /> Anterior
              </Button>
              <Button
                variant="secondary"
                disabled={filters.page >= lastPage}
                onClick={() => update({ page: filters.page + 1 })}
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

export default function CasesPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense fallback={<LoadingState />}>
      <CasesList />
    </Suspense>
  );
}
