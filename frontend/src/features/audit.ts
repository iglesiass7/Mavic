/** Auditoría (ADR-036): quién hizo qué y cuándo. Solo lectura. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { AuditCategory, AuditEvent, AuditLevel, IsoDate, Page } from "@/lib/types";

export const AUDIT_PAGE_SIZE = 20;

export const CATEGORY_LABEL: Record<AuditCategory, string> = {
  settings: "Configuración (reglas, usuarios, avisos, tarifas)",
  portfolio: "Cartera (cargas y casos)",
  calls: "Llamadas y acuerdos",
  payments: "Pagos",
  reminders: "Avisos enviados",
};

export const LEVEL_LABEL: Record<AuditLevel, string> = {
  critical: "Crítico",
  info: "Operación",
  system: "Sistema",
};

/** Qué pasó, en pocas palabras (la columna "Evento"). */
export const ACTION_LABEL: Record<string, string> = {
  RULE_CREATED: "Regla creada",
  RULE_UPDATED: "Cambio de regla",
  USER_CREATED: "Alta de usuario",
  USER_UPDATED: "Cambio de usuario",
  PASSWORD_CHANGED: "Cambio de contraseña",
  COMPANY_CREATED: "Alta de la empresa",
  REMINDER_SETTINGS_UPDATED: "Cambio en los avisos",
  COST_RATES_UPDATED: "Cambio de tarifas",
  INVOICES_IMPORTED: "Carga de facturas",
  CASES_GENERATED: "Casos generados",
  CASE_ESCALATED: "Caso derivado",
  CALL_STARTED: "Llamada pedida",
  CALL_FAILED: "Llamada fallida",
  CALL_FINISHED: "Llamada terminada",
  CALL_NEEDS_REVIEW: "Llamada para revisar",
  AGREEMENT_CREATED: "Acuerdo de pago",
  PAYMENT_RECORDED: "Pago registrado",
  PAYMENT_UNDONE: "Pago anulado",
  AGREEMENT_FULFILLED: "Acuerdo cumplido",
  REMINDERS_SENT: "Avisos enviados",
  REMINDERS_NOT_SENT: "Avisos sin enviar",
};

export interface AuditFilters {
  search: string;
  category: AuditCategory | "";
  level: AuditLevel | "";
  since: IsoDate | "";
  until: IsoDate | "";
  page: number;
}

export const DEFAULT_AUDIT_FILTERS: AuditFilters = {
  search: "",
  category: "",
  level: "",
  since: "",
  until: "",
  page: 1,
};

function query(filters: AuditFilters, limit: number, offset: number) {
  return {
    q: filters.search.trim() || undefined,
    category: filters.category || undefined,
    level: filters.level || undefined,
    since: filters.since || undefined,
    until: filters.until || undefined,
    limit,
    offset,
  };
}

export function useAuditEvents(filters: AuditFilters) {
  return useQuery({
    queryKey: ["audit", filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<AuditEvent>>("/audit-events", {
        query: query(filters, AUDIT_PAGE_SIZE, (filters.page - 1) * AUDIT_PAGE_SIZE),
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

/** Hasta 1.000 eventos con los filtros de la pantalla, para "Descargar registros". */
export async function fetchAllEvents(filters: AuditFilters, max = 1000): Promise<AuditEvent[]> {
  const all: AuditEvent[] = [];
  for (let offset = 0; offset < max; offset += 100) {
    const page = await apiFetch<Page<AuditEvent>>("/audit-events", { query: query(filters, 100, offset) });
    all.push(...page.items);
    if (all.length >= page.total || page.items.length === 0) break;
  }
  return all;
}

/** Los eventos como CSV (separado por ";" y con BOM: Excel en castellano lo abre bien). */
export function eventsToCsv(events: AuditEvent[], formatInstant: (iso: string) => string): string {
  const cell = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const header = ["Fecha y hora", "Quién", "Evento", "Sobre", "Detalle", "Nivel", "Id"];
  const rows = events.map((e) => [
    formatInstant(e.occurred_at),
    e.actor_name,
    ACTION_LABEL[e.action] ?? e.action,
    e.subject_label ?? "",
    e.summary,
    LEVEL_LABEL[e.level],
    e.id,
  ]);
  return `﻿${[header, ...rows].map((row) => row.map(cell).join(";")).join("\r\n")}\r\n`;
}
