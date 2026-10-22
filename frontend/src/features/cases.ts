/** Pedidos al backend sobre casos: lista, detalle, ofertas y llamadas. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  CaseDetail,
  CaseOffers,
  CaseSort,
  CaseStatus,
  CaseSummary,
  Conversation,
  Page,
  StartedCall,
} from "@/lib/types";

export const PAGE_SIZE = 20;

export interface CaseFilters {
  status: CaseStatus | "";
  sort: CaseSort;
  page: number; // empieza en 1
}

export function useCases(filters: CaseFilters) {
  return useQuery({
    queryKey: ["cases", filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<CaseSummary>>("/cases", {
        query: {
          status: filters.status,
          sort: filters.sort,
          limit: PAGE_SIZE,
          offset: (filters.page - 1) * PAGE_SIZE,
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
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
  });
}

/** Una llamada que todavía puede cambiar (aún no llegó su webhook). */
export function isCallOngoing(call: Conversation): boolean {
  return call.status === "INITIATING" || call.status === "INITIATED" || call.status === "IN_PROGRESS";
}
