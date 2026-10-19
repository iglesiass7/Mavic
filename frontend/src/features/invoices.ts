/** Pedidos al backend sobre facturas: lista, carga de archivos y generación de casos. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { GenerationResult, ImportRecord, ImportReport, Invoice, Page } from "@/lib/types";

export const INVOICES_PAGE_SIZE = 20;

/**
 * Qué facturas mostrar. Son los filtros que entiende GET /invoices:
 * - all          todas
 * - unassigned   vencidas que todavía no están en un caso (las que agrupa "Generar casos")
 * - in_case      las que ya están en un caso
 */
export type InvoiceFilter = "all" | "unassigned" | "in_case";

const FILTER_QUERY: Record<InvoiceFilter, Record<string, boolean | undefined>> = {
  all: {},
  unassigned: { in_case: false, overdue_only: true },
  in_case: { in_case: true },
};

export function useInvoices(filter: InvoiceFilter, page: number) {
  return useQuery({
    queryKey: ["invoices", filter, page],
    queryFn: ({ signal }) =>
      apiFetch<Page<Invoice>>("/invoices", {
        query: {
          ...FILTER_QUERY[filter],
          limit: INVOICES_PAGE_SIZE,
          offset: (page - 1) * INVOICES_PAGE_SIZE,
        },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

/** Cuántas facturas vencidas esperan que se generen los casos. */
export function useUnassignedOverdueCount() {
  return useQuery({
    queryKey: ["invoices", "unassigned", "count"],
    queryFn: ({ signal }) =>
      apiFetch<Page<Invoice>>("/invoices", {
        query: { ...FILTER_QUERY.unassigned, limit: 1 },
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
