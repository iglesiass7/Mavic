"use client";

/**
 * La tabla de Rynx: buscador arriba, columnas que se ordenan con un clic y
 * paginación abajo ("Filas por página", "Página 1 de 4", ⏮ ◀ ▶ ⏭).
 *
 * No guarda datos ni filtra: muestra las filas que recibe y avisa los cambios
 * (búsqueda, orden, página). Así sirve igual para listas que pagina el backend
 * (casos, facturas) y para listas chicas que se filtran en el navegador.
 */
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
} from "lucide-react";
import type { ReactNode } from "react";

import { count } from "@/lib/format";

import { Card, LoadingState, cx } from "./ui";

export interface Column<Row> {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  /** Si se puede ordenar: el valor de `sort` que manda (y "-valor" al invertir). */
  sortKey?: string;
  className?: string;
  headerClassName?: string;
}

export const PAGE_SIZES = [10, 20, 50];

/** Siguiente orden al hacer clic en una columna: asc -> desc -> asc. */
export function nextSort(current: string, key: string): string {
  return current === key ? `-${key}` : key;
}

export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  caption,
  search,
  sort,
  onSort,
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  loading = false,
  empty,
  toolbar,
  onRowClick,
}: {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  caption: string;
  search?: { value: string; onChange: (value: string) => void; placeholder?: string };
  sort?: string;
  onSort?: (sort: string) => void;
  page?: number; // empieza en 1
  pageSize?: number;
  total?: number;
  onPage?: (page: number) => void;
  onPageSize?: (size: number) => void;
  loading?: boolean;
  empty?: ReactNode;
  toolbar?: ReactNode;
  onRowClick?: (row: Row) => void;
}) {
  const pages = total !== undefined && pageSize ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  const current = Math.min(page ?? 1, pages);

  return (
    <Card className="p-4">
      {(search || toolbar) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {search && (
            <label className="relative w-full max-w-sm">
              <span className="sr-only">Buscar</span>
              <Search
                aria-hidden
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-gray-500"
              />
              <input
                type="search"
                value={search.value}
                onChange={(event) => search.onChange(event.target.value)}
                placeholder={search.placeholder ?? "Buscar en toda la tabla..."}
                className="w-full rounded-lg border border-gray-300 bg-white py-2.5 pr-3 pl-9 text-sm placeholder:text-gray-500"
              />
            </label>
          )}
          {toolbar}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-sunken text-left">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={ariaSort(sort, column.sortKey)}
                  className={cx("px-4 py-3 font-bold whitespace-nowrap text-ink", column.headerClassName)}
                >
                  {column.sortKey && onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(nextSort(sort ?? "", column.sortKey!))}
                      className="inline-flex items-center gap-1.5 hover:text-rynx-primary"
                    >
                      {column.header}
                      <SortIcon sort={sort} sortKey={column.sortKey} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4">
                  <LoadingState />
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10 text-center text-muted">
                  {empty ?? "No hay resultados."}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cx(
                    "border-t border-line",
                    onRowClick && "cursor-pointer hover:bg-sunken/60",
                    loading && "opacity-60",
                  )}
                >
                  {columns.map((column) => (
                    <td key={column.key} className={cx("px-4 py-3 align-middle", column.className)}>
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {total !== undefined && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
          <p>{count(total, "fila", "filas")}</p>
          {onPage && pageSize && (
            <div className="flex flex-wrap items-center gap-3">
              {onPageSize && (
                <label className="flex items-center gap-2">
                  Filas por página
                  <select
                    value={pageSize}
                    onChange={(event) => onPageSize(Number(event.target.value))}
                    className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-ink"
                  >
                    {PAGE_SIZES.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <span className="tabular">
                Página {current} de {pages}
              </span>
              <div className="flex gap-1">
                <PageButton label="Primera página" disabled={current <= 1} onClick={() => onPage(1)}>
                  <ChevronsLeft className="size-4" />
                </PageButton>
                <PageButton
                  label="Página anterior"
                  disabled={current <= 1}
                  onClick={() => onPage(current - 1)}
                >
                  <ChevronLeft className="size-4" />
                </PageButton>
                <PageButton
                  label="Página siguiente"
                  disabled={current >= pages}
                  onClick={() => onPage(current + 1)}
                >
                  <ChevronRight className="size-4" />
                </PageButton>
                <PageButton
                  label="Última página"
                  disabled={current >= pages}
                  onClick={() => onPage(pages)}
                >
                  <ChevronsRight className="size-4" />
                </PageButton>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function ariaSort(sort: string | undefined, key: string | undefined) {
  if (!key || !sort) return undefined;
  if (sort === key) return "ascending" as const;
  if (sort === `-${key}`) return "descending" as const;
  return undefined;
}

function SortIcon({ sort, sortKey }: { sort?: string; sortKey: string }) {
  if (sort === sortKey) return <ArrowUp aria-hidden className="size-3.5" />;
  if (sort === `-${sortKey}`) return <ArrowDown aria-hidden className="size-3.5" />;
  return <ArrowUpDown aria-hidden className="size-3.5 text-gray-400" />;
}

function PageButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="flex size-9 items-center justify-center rounded-lg border border-gray-300 bg-white text-ink hover:bg-sunken disabled:text-gray-300"
    >
      <span aria-hidden>{children}</span>
    </button>
  );
}
