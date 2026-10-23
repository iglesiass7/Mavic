"use client";

/**
 * El botón de avisos en Facturas (grupos 1 y 2), como "Enviar recordatorios" de Rynx:
 *
 *   Aviso preventivo por Email · vencen del 17/10 al 21/10
 *   3 por mandar · 2 ya avisadas · 1 sin email          [Enviar 3 avisos]
 *   Envío automático: todos los días a las 09:00 (o apagado)
 *
 * Antes de mandar, muestra el primer aviso tal como va a salir y pide confirmar.
 */
import { CheckCircle2, Mail, MessageCircle, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  CHANNEL_LABEL,
  CHANNEL_SETUP,
  STAGE_LABEL,
  useNoticePreview,
  useSendNotices,
} from "@/features/notices";
import { count, formatDate } from "@/lib/format";
import type { NoticeSendReport, NoticeStage } from "@/lib/types";

import { Button, QueryError } from "./ui";

const SETTINGS_TAB: Record<NoticeStage, string> = { preventive: "preventivo", due_today: "corriente" };

function reportText(report: NoticeSendReport): string {
  const parts = [
    `${count(report.sent, "aviso mandado", "avisos mandados")} por ${CHANNEL_LABEL[report.channel]}`,
  ];
  if (report.failed) parts.push(count(report.failed, "falló", "fallaron"));
  if (report.without_contact) parts.push(`${report.without_contact} sin datos de contacto`);
  if (report.remaining) parts.push(`quedan ${report.remaining}: volvé a apretar el botón`);
  return `${parts.join(", ")}.`;
}

export function NoticeAction({ stage, canOperate }: { stage: NoticeStage; canOperate: boolean }) {
  const preview = useNoticePreview(stage);
  const send = useSendNotices(stage);
  const [confirming, setConfirming] = useState(false);

  if (preview.isError) return <QueryError error={preview.error} retry={preview.refetch} />;
  if (!preview.isSuccess) return null;
  const p = preview.data;
  const Icon = p.channel === "email" ? Mail : MessageCircle;
  const window =
    p.first_due === p.last_due
      ? `vencen el ${formatDate(p.first_due)}`
      : `vencen del ${formatDate(p.first_due)} al ${formatDate(p.last_due)}`;

  return (
    <section
      aria-label={STAGE_LABEL[stage]}
      className="rounded-2xl border border-petrol/25 bg-petrol-soft px-5 py-4"
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <Icon aria-hidden className="size-5 shrink-0 text-rynx-primary" />
        <div className="min-w-60 flex-1">
          <p className="font-semibold">
            {STAGE_LABEL[stage]} por {CHANNEL_LABEL[p.channel]}: facturas que {window}
          </p>
          <p className="mt-0.5 text-sm text-muted">
            {count(p.to_send, "por mandar", "por mandar")}
            {p.already_sent > 0 && ` · ${count(p.already_sent, "ya avisada", "ya avisadas")}`}
            {p.without_contact > 0 &&
              ` · ${p.without_contact} sin ${p.channel === "email" ? "email" : "teléfono"}`}
            {" · "}
            {p.enabled
              ? `Envío automático: todos los días a las ${p.send_time}`
              : "Envío automático apagado"}{" "}
            (
            <Link
              href={`/rules?tramo=${SETTINGS_TAB[stage]}`}
              className="font-semibold text-rynx-primary underline"
            >
              configurar
            </Link>
            )
          </p>
        </div>
        {canOperate && p.to_send > 0 && p.channel_ready && !confirming && (
          <Button
            onClick={() => {
              send.reset();
              setConfirming(true);
            }}
          >
            <Send aria-hidden className="size-4" /> Enviar {count(p.to_send, "aviso", "avisos")}
          </Button>
        )}
      </div>

      {!p.channel_ready && (
        <p className="mt-3 text-sm text-status-escalated">
          {CHANNEL_LABEL[p.channel]} no está configurado en el servidor: faltan {CHANNEL_SETUP[p.channel]} en
          el .env.
        </p>
      )}

      {confirming && (
        <div className="mt-4 rounded-xl border border-gray-300 bg-white p-4">
          <p className="text-sm font-semibold">
            Se van a mandar {count(p.to_send, "aviso", "avisos")} por {CHANNEL_LABEL[p.channel]}. Así sale el
            primero:
          </p>
          <div className="mt-3 rounded-xl bg-sunken/60 px-4 py-3 text-sm whitespace-pre-line">
            {p.sample_subject && <p className="mb-2 font-bold">{p.sample_subject}</p>}
            {p.sample_body}
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              loading={send.isPending}
              onClick={() => send.mutate(undefined, { onSettled: () => setConfirming(false) })}
            >
              Confirmar envío
            </Button>
            <Button variant="ghost" disabled={send.isPending} onClick={() => setConfirming(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {send.isSuccess && (
        <div role="status" className="mt-3 text-sm">
          <p className="flex items-center gap-2">
            <CheckCircle2 aria-hidden className="size-4 text-status-agreement" /> {reportText(send.data)}
          </p>
          {send.data.errors.length > 0 && (
            <ul className="mt-2 list-disc pl-6 text-xs text-status-disputed">
              {send.data.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {send.isError && (
        <div className="mt-3">
          <QueryError error={send.error} retry={() => send.mutate()} />
        </div>
      )}
    </section>
  );
}
