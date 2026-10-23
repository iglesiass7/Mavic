/** Pedidos al backend para la pantalla Conversaciones: todas las llamadas de la empresa. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  CallListItem,
  CallOutcomeFilter,
  CaseStatus,
  Conversation,
  IsoDate,
  Page,
} from "@/lib/types";

import { isCallOngoing } from "./cases";

export const CALLS_PAGE_SIZE = 30;

export interface CallFilters {
  search: string;
  outcome: CallOutcomeFilter | "";
  day: IsoDate | "";
  page: number;
}

export function useCompanyCalls(filters: CallFilters) {
  return useQuery({
    queryKey: ["calls", filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<CallListItem>>("/conversations", {
        query: {
          q: filters.search.trim() || undefined,
          outcome: filters.outcome || undefined,
          day: filters.day || undefined,
          limit: CALLS_PAGE_SIZE,
          offset: (filters.page - 1) * CALLS_PAGE_SIZE,
        },
        signal,
      }),
    placeholderData: keepPreviousData,
    // Mientras haya una llamada en curso, se vuelve a pedir cada 10 segundos.
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => isCallOngoing(item.call)) ? 10_000 : false,
  });
}

/** La conversación como texto, para "Descargar chat". */
export function transcriptText(item: CallListItem): string {
  const lines = [
    `Caso #${item.case_number} · ${item.debtor_name}`,
    `Llamada del ${new Date(item.call.started_at).toLocaleString("es-AR")}`,
    "",
  ];
  if (item.call.summary) lines.push(`Resumen: ${item.call.summary}`, "");
  for (const turn of item.call.transcript ?? []) {
    const who = turn.role === "agent" ? "Agente" : "Deudor";
    const at = turn.time_in_call_secs === null ? "" : ` [${formatSecs(turn.time_in_call_secs)}]`;
    lines.push(`${who}${at}: ${turn.message ?? ""}`);
  }
  return `${lines.join("\n")}\n`;
}

/** 95 -> "1:35". */
export function formatSecs(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- filtros en la dirección

/** Cómo se ve cada estado en la dirección: ?estado=acuerdo (en castellano, legible). */
export const OUTCOME_SLUG: Record<CallOutcomeFilter, string> = {
  ongoing: "en-curso",
  ACUERDO: "acuerdo",
  CONTACTADO: "contactado",
  DESCONOCIMIENTO: "no-reconoce",
  DERIVACION_HUMANA: "derivada",
  review: "para-revisar",
  failed: "fallida",
};

const OUTCOME_BY_SLUG = new Map(
  Object.entries(OUTCOME_SLUG).map(([outcome, slug]) => [slug, outcome as CallOutcomeFilter]),
);

export const DEFAULT_CALL_FILTERS: CallFilters = { search: "", outcome: "", day: "", page: 1 };

/** Lee los filtros de la URL, ignorando valores inventados (?estado=cualquiera). */
export function readCallFilters(params: URLSearchParams): CallFilters {
  const day = params.get("fecha") ?? "";
  const page = Number(params.get("pagina"));
  return {
    search: params.get("q") ?? "",
    outcome: OUTCOME_BY_SLUG.get(params.get("estado") ?? "") ?? "",
    day: /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : "",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

/** Lo contrario: los filtros como texto para la dirección (sin los que están vacíos). */
export function callFiltersQuery(filters: CallFilters, callId: string | null): string {
  const query = new URLSearchParams();
  if (filters.search.trim()) query.set("q", filters.search.trim());
  if (filters.outcome) query.set("estado", OUTCOME_SLUG[filters.outcome]);
  if (filters.day) query.set("fecha", filters.day);
  if (filters.page > 1) query.set("pagina", String(filters.page));
  if (callId) query.set("llamada", callId);
  return query.toString();
}

// ---------------------------------------------------------------- cómo terminó

/**
 * Cómo terminó una llamada, en pocas palabras y con el color del estado de caso
 * que le corresponde (el color nunca va solo: siempre lleva el texto).
 */
export function callOutcome(call: Conversation): { label: string; tone: CaseStatus } {
  if (isCallOngoing(call)) return { label: "En curso", tone: "pending" };
  if (call.status === "FAILED") return { label: "No se pudo llamar", tone: "disputed" };
  if (call.status === "NEEDS_REVIEW") return { label: "Para revisar", tone: "escalated" };
  switch (call.result) {
    case "ACUERDO":
      return { label: "Acuerdo", tone: "agreement" };
    case "CONTACTADO":
      return { label: "Contactado", tone: "contacted" };
    case "DESCONOCIMIENTO":
      return { label: "No reconoce", tone: "disputed" };
    case "DERIVACION_HUMANA":
      return { label: "Derivada", tone: "escalated" };
    default:
      return { label: "Terminada", tone: "closed" };
  }
}
