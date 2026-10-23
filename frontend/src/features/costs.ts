/** Medidor de costos (ADR-039): uso del mes × tarifas de la empresa. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { BudgetStatus, CostConcept, CostRates, MonthCosts } from "@/lib/types";

export const CONCEPT_LABEL: Record<CostConcept, string> = {
  calls: "Llamadas del agente",
  email: "Avisos por email",
  whatsapp: "Avisos por WhatsApp",
};

export const CONCEPT_UNIT: Record<CostConcept, string> = {
  calls: "por minuto",
  email: "por email",
  whatsapp: "por mensaje",
};

export const BUDGET_LABEL: Record<BudgetStatus, string> = {
  no_budget: "Sin tope cargado",
  ok: "Consumo dentro del tope",
  high: "Consumo alto (más del 80 % del tope)",
  over_projection: "La proyección supera el tope",
  over_budget: "Se superó el tope",
};

export function useMonthCosts(month: string) {
  return useQuery({
    queryKey: ["costs", month],
    queryFn: ({ signal }) => apiFetch<MonthCosts>("/costs", { query: { month }, signal }),
  });
}

export function useCostRates() {
  return useQuery({
    queryKey: ["cost-rates"],
    queryFn: ({ signal }) => apiFetch<CostRates>("/cost-rates", { signal }),
  });
}

export type RatesInput = Omit<CostRates, "configured">;

export function useSaveCostRates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RatesInput) => apiFetch<CostRates>("/cost-rates", { method: "PUT", json: body }),
    onSuccess: (data) => {
      queryClient.setQueryData(["cost-rates"], data);
      return queryClient.invalidateQueries({ queryKey: ["costs"] });
    },
  });
}

/** "2026-10" del mes actual (hora argentina). */
export function currentMonth(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Argentina/Buenos_Aires",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}`;
}

/** "2026-10" -> "octubre de 2026". */
export function monthName(month: string): string {
  const [year, m] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("es-AR", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year ?? 2026, (m ?? 1) - 1, 1)),
  );
}

/** El mes anterior o siguiente: shiftMonth("2026-01", -1) -> "2025-12". */
export function shiftMonth(month: string, delta: number): string {
  const [year, m] = month.split("-").map(Number);
  const index = (year ?? 2026) * 12 + ((m ?? 1) - 1) + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}
