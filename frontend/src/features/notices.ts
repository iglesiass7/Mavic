/**
 * Avisos por email y WhatsApp (ADR-038): configuración, vista previa, el botón
 * de Facturas y el último aviso de cada factura.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  InvoiceNotice,
  NoticeChannel,
  NoticePreview,
  NoticeSendReport,
  NoticeSettings,
  NoticeStage,
  NoticeStageSettings,
} from "@/lib/types";

export const STAGE_LABEL: Record<NoticeStage, string> = {
  preventive: "Aviso preventivo",
  due_today: "Aviso del día de vencimiento",
};

export const CHANNEL_LABEL: Record<NoticeChannel, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
};

/** Qué falta en el .env para usar cada canal (se muestra si no está configurado). */
export const CHANNEL_SETUP: Record<NoticeChannel, string> = {
  email: "SMTP_HOST y SMTP_FROM",
  whatsapp: "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM",
};

const SETTINGS_KEY = ["notice-settings"];

export function useNoticeSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: ({ signal }) => apiFetch<NoticeSettings>("/notice-settings", { signal }),
  });
}

export type NoticeSettingsInput = Omit<NoticeStageSettings, "stage">;

export function useSaveNoticeSettings(stage: NoticeStage) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: NoticeSettingsInput) =>
      apiFetch<NoticeSettings>(`/notice-settings/${stage}`, { method: "PUT", json: body }),
    onSuccess: (data) => {
      queryClient.setQueryData(SETTINGS_KEY, data);
      return queryClient.invalidateQueries({ queryKey: ["notice-preview"] });
    },
  });
}

export function useNoticePreview(stage: NoticeStage | null) {
  return useQuery({
    queryKey: ["notice-preview", stage],
    queryFn: ({ signal }) => apiFetch<NoticePreview>("/notices/preview", { query: { stage }, signal }),
    enabled: stage !== null,
  });
}

export function useSendNotices(stage: NoticeStage) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<NoticeSendReport>("/notices/send", { method: "POST", json: { stage } }),
    onSettled: () =>
      Promise.all(
        [["notice-preview"], ["invoice-notices"]].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

/** El último aviso de cada factura de la página (para la columna "Aviso"). */
export function useInvoiceNotices(invoiceIds: string[]) {
  return useQuery({
    queryKey: ["invoice-notices", invoiceIds],
    queryFn: ({ signal }) =>
      apiFetch<InvoiceNotice[]>("/notices", { query: { invoice_id: invoiceIds }, signal }),
    enabled: invoiceIds.length > 0,
    placeholderData: keepPreviousData,
  });
}

/**
 * Arma el texto de ejemplo con datos inventados, para ver el mensaje mientras se escribe.
 * Es la misma regla que usa el backend: cada {marcador} conocido se reemplaza; el resto queda.
 */
export const SAMPLE_VALUES: Record<string, string> = {
  nombre: "Ana Torres",
  empresa: "Tu empresa",
  numero_factura: "FS-1004",
  concepto: "Abono internet octubre",
  monto: "$ 24.000,00",
  vencimiento: "25/10/2026",
  dias: "5",
  instrucciones: "",
};

export function renderSample(text: string, values: Record<string, string>): string {
  return text.replace(/\{([^{}]*)\}/g, (whole, name: string) => values[name] ?? whole);
}

/** Los marcadores que no existen ("{nombr}"): se avisa antes de guardar. */
export function unknownPlaceholders(text: string, known: string[]): string[] {
  return [...text.matchAll(/\{([^{}]*)\}/g)].map((m) => m[1] ?? "").filter((name) => !known.includes(name));
}
