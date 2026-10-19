/** Pedidos al backend sobre casos: lista, detalle, ofertas y llamadas. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  CaseDetail,
  CaseOffers,
  CaseSort,
  CaseStatus,
  CaseSummary,
  Conversation,
  Page,
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
  });
}
