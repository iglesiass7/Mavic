/** Pedidos al backend sobre casos: lista, detalle, ofertas y llamadas. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { CASE_STATUS_LABEL } from "@/lib/labels";
import type {
  AmountPage,
  CaseDetail,
  CaseOffers,
  CaseSort,
  CaseStatus,
  CaseSummary,
  Conversation,
  StartedCall,
} from "@/lib/types";

export const PAGE_SIZE = 10; // como Rynx: 10 filas por página (se puede cambiar)

export interface CaseFilters {
  status: CaseStatus | "";
  search: string;
  minAmount: number | null;
  maxAmount: number | null;
  sort: CaseSort;
  page: number; // empieza en 1
  pageSize: number;
}

export const DEFAULT_CASE_FILTERS: CaseFilters = {
  status: "",
  search: "",
  minAmount: null,
  maxAmount: null,
  sort: "oldest_debt",
  page: 1,
  pageSize: PAGE_SIZE,
};

export const CASE_STATUSES = Object.keys(CASE_STATUS_LABEL) as CaseStatus[];
const SORTS: CaseSort[] = [
  "oldest_debt", "highest_amount", "newest", "number", "-number", "debtor", "-debtor",
  "document", "-document", "amount", "-amount", "invoices", "-invoices", "status", "-status",
];

function numberOrNull(value: string | null): number | null {
  const n = Number(value);
  return value !== null && value !== "" && Number.isFinite(n) && n >= 0 ? n : null;
}

/** Lee los filtros de la URL, ignorando valores inventados (?estado=cualquiera). */
export function readCaseFilters(params: URLSearchParams): CaseFilters {
  const status = params.get("estado") as CaseStatus;
  const sort = params.get("orden") as CaseSort;
  const page = Number(params.get("pagina"));
  const size = Number(params.get("filas"));
  return {
    status: CASE_STATUSES.includes(status) ? status : "",
    search: params.get("q") ?? "",
    minAmount: numberOrNull(params.get("desde")),
    maxAmount: numberOrNull(params.get("hasta")),
    sort: SORTS.includes(sort) ? sort : DEFAULT_CASE_FILTERS.sort,
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: [10, 20, 50].includes(size) ? size : DEFAULT_CASE_FILTERS.pageSize,
  };
}

export function useCases(filters: CaseFilters) {
  return useQuery({
    queryKey: ["cases", filters],
    queryFn: ({ signal }) =>
      apiFetch<AmountPage<CaseSummary>>("/cases", {
        query: {
          status: filters.status,
          q: filters.search.trim() || undefined,
          min_amount: filters.minAmount ?? undefined,
          max_amount: filters.maxAmount ?? undefined,
          sort: filters.sort,
          limit: filters.pageSize,
          offset: (filters.page - 1) * filters.pageSize,
        },
        signal,
      }),
    // Al cambiar de página se sigue viendo la anterior hasta que llega la nueva
    // (sin parpadeo de "cargando").
    placeholderData: keepPreviousData,
  });
}

export function useCase(caseId: string) {
  return useQuery({
    queryKey: ["case", caseId],
    queryFn: ({ signal }) => apiFetch<CaseDetail>(`/cases/${caseId}`, { signal }),
  });
}

export function useCaseOffers(caseId: string) {
  return useQuery({
    queryKey: ["case", caseId, "offers"],
    queryFn: ({ signal }) => apiFetch<CaseOffers>(`/cases/${caseId}/offers`, { signal }),
  });
}

export function useCaseConversations(caseId: string) {
  return useQuery({
    queryKey: ["case", caseId, "conversations"],
    queryFn: ({ signal }) =>
      apiFetch<Conversation[]>(`/cases/${caseId}/conversations`, { signal }),
    refetchInterval: (query) =>
      query.state.data?.some((call) => isCallOngoing(call)) ? 10_000 : false,
  });
}

/**
 * "Llamar al deudor": Mavic le pide a ElevenLabs que llame (POST /cases/{id}/calls).
 * El resultado llega minutos después por el webhook: por eso la lista de llamadas
 * se vuelve a pedir sola cada 10 segundos mientras haya una en curso.
 */
export function useStartCall(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<StartedCall>(`/cases/${caseId}/calls`, { method: "POST" }),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["calls"] }),
      ]),
  });
}

/**
 * "Derivar a humano": el caso pasa a "derivado" y el agente deja de llamarlo.
 * Cambia el estado del caso, así que se refresca todo lo que lo muestra.
 */
export function useEscalateCase(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<CaseDetail>(`/cases/${caseId}/escalate`, { method: "POST" }),
    onSettled: () =>
      Promise.all(
        [["case", caseId], ["cases"], ["calls"], ["dashboard"]].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

/** Una llamada que todavía puede cambiar (aún no llegó su webhook). */
export function isCallOngoing(call: Conversation): boolean {
  return call.status === "INITIATING" || call.status === "INITIATED" || call.status === "IN_PROGRESS";
}
