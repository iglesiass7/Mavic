/** Pedidos al backend sobre facturas: lista, carga de archivos y generación de casos. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PAGE_SIZES } from "@/components/DataTable";
import { apiFetch } from "@/lib/api";
import type {
  AmountPage,
  GenerationResult,
  ImportRecord,
  ImportReport,
  Invoice,
  InvoiceSort,
  InvoiceStage,
} from "@/lib/types";

export const INVOICES_PAGE_SIZE = 10;

/**
 * Los tres grupos de la pantalla de facturas (como en Rynx), según el vencimiento:
 *   1. upcoming   próximas a vencer
 *   2. due_today  vencen hoy
 *   3. overdue    vencidas (las que pueden ir a un caso)
 */
export type InvoiceGroup = InvoiceStage;

/** Dentro de las vencidas: todas, las que esperan caso o las que ya están en uno. */
export type CaseFilter = "all" | "unassigned" | "in_case";

const CASE_FILTER_QUERY: Record<CaseFilter, boolean | undefined> = {
  all: undefined,
  unassigned: false,
  in_case: true,
};

export interface InvoiceFilters {
  group: InvoiceGroup;
  inCase: CaseFilter;
  search: string;
  minAmount: number | null;
  maxAmount: number | null;
  sort: InvoiceSort;
  page: number;
  pageSize: number;
}

// ---------------------------------------------------------------- filtros en la dirección

// En la dirección se usan palabras en español: /invoices?grupo=vencidas
const GROUP_SLUG: Record<InvoiceGroup, string> = {
  upcoming: "proximas",
  due_today: "hoy",
  overdue: "vencidas",
};
const CASE_FILTER_SLUG: Record<CaseFilter, string> = {
  all: "",
  unassigned: "sin-caso",
  in_case: "en-caso",
};
const SORTS: InvoiceSort[] = [
  "due_date", "-due_date", "amount", "-amount", "external_id", "-external_id",
  "description", "-description", "debtor", "-debtor",
];

export const DEFAULT_INVOICE_FILTERS: InvoiceFilters = {
  group: "upcoming",
  inCase: "all",
  search: "",
  minAmount: null,
  maxAmount: null,
  sort: "due_date",
  page: 1,
  pageSize: INVOICES_PAGE_SIZE,
};

function numberOrNull(value: string | null): number | null {
  const n = Number(value);
  return value !== null && value !== "" && Number.isFinite(n) && n >= 0 ? n : null;
}

function keyOf<K extends string>(map: Record<K, string>, slug: string | null, fallback: K): K {
  const found = (Object.keys(map) as K[]).find((key) => map[key] === slug);
  return found ?? fallback;
}

/** Lee los filtros de la URL, ignorando valores inventados (?grupo=cualquiera). */
export function readInvoiceFilters(params: URLSearchParams): InvoiceFilters {
  const sort = params.get("orden") as InvoiceSort;
  const page = Number(params.get("pagina"));
  const size = Number(params.get("filas"));
  // Compatibilidad con los links viejos del tablero: ?filter=unassigned
  const legacy = params.get("filter") === "unassigned";
  const group = legacy ? "overdue" : keyOf(GROUP_SLUG, params.get("grupo"), DEFAULT_INVOICE_FILTERS.group);
  return {
    group,
    inCase: legacy ? "unassigned" : keyOf(CASE_FILTER_SLUG, params.get("casos"), "all"),
    search: params.get("q") ?? "",
    minAmount: numberOrNull(params.get("desde")),
    maxAmount: numberOrNull(params.get("hasta")),
    sort: SORTS.includes(sort) ? sort : DEFAULT_INVOICE_FILTERS.sort,
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: PAGE_SIZES.includes(size) ? size : DEFAULT_INVOICE_FILTERS.pageSize,
  };
}

export function invoiceFiltersQuery(filters: InvoiceFilters): string {
  const query = new URLSearchParams();
  if (filters.group !== DEFAULT_INVOICE_FILTERS.group) query.set("grupo", GROUP_SLUG[filters.group]);
  if (filters.group === "overdue" && filters.inCase !== "all") {
    query.set("casos", CASE_FILTER_SLUG[filters.inCase]);
  }
  if (filters.search.trim()) query.set("q", filters.search.trim());
  if (filters.minAmount !== null) query.set("desde", String(filters.minAmount));
  if (filters.maxAmount !== null) query.set("hasta", String(filters.maxAmount));
  if (filters.sort !== DEFAULT_INVOICE_FILTERS.sort) query.set("orden", filters.sort);
  if (filters.page > 1) query.set("pagina", String(filters.page));
  if (filters.pageSize !== DEFAULT_INVOICE_FILTERS.pageSize) query.set("filas", String(filters.pageSize));
  return query.toString();
}


export function useInvoices(filters: InvoiceFilters) {
  return useQuery({
    queryKey: ["invoices", filters],
    queryFn: ({ signal }) =>
      apiFetch<AmountPage<Invoice>>("/invoices", {
        query: {
          stage: filters.group,
          in_case: CASE_FILTER_QUERY[filters.inCase],
          q: filters.search.trim() || undefined,
          min_amount: filters.minAmount ?? undefined,
          max_amount: filters.maxAmount ?? undefined,
          sort: filters.sort,
          limit: filters.pageSize,
          offset: (filters.page - 1) * filters.pageSize,
        },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

/** Cuántas facturas hay en cada grupo (el número al lado de "Grupo 1", "Grupo 2"...). */
export function useInvoiceGroupCounts() {
  return useQuery({
    queryKey: ["invoices", "group-counts"],
    queryFn: async ({ signal }) => {
      const groups: InvoiceGroup[] = ["upcoming", "due_today", "overdue"];
      const pages = await Promise.all(
        groups.map((stage) =>
          apiFetch<AmountPage<Invoice>>("/invoices", { query: { stage, limit: 1 }, signal }),
        ),
      );
      return Object.fromEntries(groups.map((g, i) => [g, pages[i]?.total ?? 0])) as Record<
        InvoiceGroup,
        number
      >;
    },
  });
}

/** Cuántas facturas vencidas esperan que se generen los casos. */
export function useUnassignedOverdueCount() {
  return useQuery({
    queryKey: ["invoices", "unassigned", "count"],
    queryFn: ({ signal }) =>
      apiFetch<AmountPage<Invoice>>("/invoices", {
        query: { in_case: false, overdue_only: true, limit: 1 },
        signal,
      }),
    select: (page) => page.total,
  });
}

export function useImportHistory() {
  return useQuery({
    queryKey: ["imports"],
    queryFn: ({ signal }) => apiFetch<ImportRecord[]>("/imports", { signal }),
  });
}

const MAX_BYTES = 5 * 1024 * 1024; // el mismo límite que el backend
export const ACCEPTED_EXTENSIONS = [".csv", ".xlsx"];

/** Revisión rápida en el navegador, para no subir algo que el backend va a rechazar. */
export function checkFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "El archivo tiene que ser .csv o .xlsx (Excel).";
  }
  if (file.size > MAX_BYTES) return "El archivo pesa más de 5 MB.";
  if (file.size === 0) return "El archivo está vacío.";
  return null;
}

function fileForm(file: File): FormData {
  const form = new FormData();
  form.append("file", file);
  return form;
}

/** Revisa el archivo sin guardar nada. */
export function previewImport(file: File): Promise<ImportReport> {
  return apiFetch<ImportReport>("/imports/preview", { method: "POST", formData: fileForm(file) });
}

/** Carga el archivo. Si tiene errores, el backend responde 422 y no guarda ninguna fila. */
export function importInvoices(file: File): Promise<ImportReport> {
  return apiFetch<ImportReport>("/imports", { method: "POST", formData: fileForm(file) });
}

/**
 * Después de cargar facturas o generar casos, lo que estaba en pantalla quedó
 * viejo: se marca para volver a pedirlo.
 */
function useRefreshPortfolio() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["invoices"] }),
      queryClient.invalidateQueries({ queryKey: ["imports"] }),
      queryClient.invalidateQueries({ queryKey: ["cases"] }),
      queryClient.invalidateQueries({ queryKey: ["case"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
}

export function useImportInvoices() {
  const refresh = useRefreshPortfolio();
  return useMutation({ mutationFn: importInvoices, onSuccess: refresh });
}

export function useGenerateCases() {
  const refresh = useRefreshPortfolio();
  return useMutation({
    mutationFn: () => apiFetch<GenerationResult>("/cases/generate", { method: "POST" }),
    onSuccess: refresh,
  });
}
