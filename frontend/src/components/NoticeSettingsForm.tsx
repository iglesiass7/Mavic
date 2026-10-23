"use client";

/**
 * Configuración de un aviso (pestañas Preventivo y Corriente de Reglas de negocio),
 * con el diseño de Rynx:
 *
 *   Avisos preventivos                                   [Guardar cambios]
 *   General   [envío automático]  [canal]  [días antes]  [hora]
 *   Mensaje   asunto · texto con {marcadores} · cómo pagar   |  así lo recibe el deudor
 *
 * El texto de la derecha se arma mientras se escribe, con datos de ejemplo. Los
 * marcadores que no existen se marcan antes de guardar (el backend también los rechaza).
 */
import { AlertTriangle, CheckCircle2, Mail, MessageCircle } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import {
  CHANNEL_LABEL,
  CHANNEL_SETUP,
  SAMPLE_VALUES,
  renderSample,
  unknownPlaceholders,
  useSaveNoticeSettings,
  type NoticeSettingsInput,
} from "@/features/notices";
import { errorMessage } from "@/lib/api";
import type { NoticeChannel, NoticeSettings, NoticeStageSettings } from "@/lib/types";

import { Button, ErrorState, Field, Panel, Toggle, inputClass } from "./ui";

const TEXT: Record<NoticeStageSettings["stage"], { title: string; intro: string }> = {
  preventive: {
    title: "Avisos preventivos",
    intro:
      "Un recordatorio antes de que la factura venza (grupo 1 de Facturas). Le llega una sola vez a cada factura.",
  },
  due_today: {
    title: "Aviso del día de vencimiento",
    intro:
      "Un aviso el mismo día en que vence la factura, con cómo pagar (grupo 2 de Facturas). Le llega una sola vez a cada factura.",
  },
};

function toInput(s: NoticeStageSettings): NoticeSettingsInput {
  return {
    enabled: s.enabled,
    channel: s.channel,
    send_time: s.send_time,
    days_before: s.days_before,
    email_subject: s.email_subject,
    message: s.message,
    instructions: s.instructions,
    whatsapp_template_sid: s.whatsapp_template_sid,
  };
}

export function NoticeSettingsForm({
  settings,
  data,
  canManage,
}: {
  settings: NoticeStageSettings;
  data: NoticeSettings;
  canManage: boolean;
}) {
  const save = useSaveNoticeSettings(settings.stage);
  // Lo último guardado: contra eso se compara para habilitar "Guardar cambios".
  const [saved, setSaved] = useState<NoticeSettingsInput>(() => toInput(settings));
  const [form, setForm] = useState<NoticeSettingsInput>(saved);
  const message = useRef<HTMLTextAreaElement>(null);
  const known = data.placeholders.map((p) => p.name);
  const text = TEXT[settings.stage];
  const changed = JSON.stringify(form) !== JSON.stringify(saved);
  const set = <K extends keyof NoticeSettingsInput>(key: K, value: NoticeSettingsInput[K]) => {
    save.reset();
    setForm((current) => ({ ...current, [key]: value }));
  };

  const wrongInMessage = unknownPlaceholders(form.message, known);
  const wrongInSubject = form.channel === "email" ? unknownPlaceholders(form.email_subject, known) : [];
  const ready = data.channels_ready[form.channel];

  function insert(name: string) {
    const area = message.current;
    const mark = `{${name}}`;
    if (!area) return set("message", form.message + mark);
    const start = area.selectionStart ?? form.message.length;
    const end = area.selectionEnd ?? start;
    set("message", form.message.slice(0, start) + mark + form.message.slice(end));
    requestAnimationFrame(() => {
      area.focus();
      area.setSelectionRange(start + mark.length, start + mark.length);
    });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (wrongInMessage.length || wrongInSubject.length) return;
    const body = { ...form, whatsapp_template_sid: form.whatsapp_template_sid?.trim() || null };
    save.mutate(body, {
      onSuccess: () => {
        setForm(body);
        setSaved(body);
      },
    });
  }

  const values = { ...SAMPLE_VALUES, instrucciones: form.instructions };
  // Como el backend: si "Cómo pagar" queda vacío, no quedan renglones en blanco de más.
  const preview = renderSample(form.message, values)
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-xl font-bold text-ink">{text.title}</h2>
          <p className="mt-1 text-sm text-muted">{text.intro}</p>
        </div>
        {canManage && (
          <Button type="submit" loading={save.isPending} disabled={!changed} className="px-8 py-3">
            Guardar cambios
          </Button>
        )}
      </div>

      {save.isSuccess && !changed && (
        <p role="status" className="mb-5 flex items-center gap-2 text-sm text-status-agreement">
          <CheckCircle2 aria-hidden className="size-4" /> Cambios guardados.
        </p>
      )}
      {save.isError && (
        <div className="mb-5">
          <ErrorState message={errorMessage(save.error)} />
        </div>
      )}

      <fieldset disabled={!canManage} className="space-y-6">
        <legend className="sr-only">{text.title}</legend>
        <Panel title="General">
          <div className="flex flex-wrap items-start gap-x-8 gap-y-5">
            <div>
              <p className="text-xs font-bold text-ink">Envío automático</p>
              <div className="mt-3 flex items-center gap-3">
                <Toggle
                  checked={form.enabled}
                  onChange={(on) => set("enabled", on)}
                  label="Envío automático todos los días"
                  disabled={!canManage}
                />
                <span className="text-sm text-muted">{form.enabled ? "Prendido" : "Apagado"}</span>
              </div>
            </div>
            <Field id={`${settings.stage}-channel`} label="Canal de envío" className="w-44">
              {(aria) => (
                <select
                  {...aria}
                  value={form.channel}
                  onChange={(e) => set("channel", e.target.value as NoticeChannel)}
                  className={inputClass()}
                >
                  <option value="email">Email</option>
                  <option value="whatsapp">WhatsApp</option>
                </select>
              )}
            </Field>
            {settings.stage === "preventive" && (
              <Field
                id={`${settings.stage}-days`}
                label="Días antes del vencimiento"
                hint="De 1 a 30."
                className="w-48"
              >
                {(aria) => (
                  <input
                    {...aria}
                    type="number"
                    min={1}
                    max={30}
                    value={form.days_before}
                    onChange={(e) => set("days_before", Number(e.target.value))}
                    className={inputClass()}
                  />
                )}
              </Field>
            )}
            <Field
              id={`${settings.stage}-time`}
              label="Hora del envío automático"
              hint="Hora de Argentina."
              className="w-48"
            >
              {(aria) => (
                <input
                  {...aria}
                  type="time"
                  step={60}
                  value={form.send_time}
                  onChange={(e) => set("send_time", e.target.value)}
                  className={inputClass()}
                />
              )}
            </Field>
          </div>
          {!ready && (
            <p className="mt-5 flex items-start gap-2 rounded-xl border border-status-escalated/30 bg-status-escalated/5 px-4 py-3 text-sm">
              <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-status-escalated" />
              <span>
                {CHANNEL_LABEL[form.channel]} todavía no está configurado en el servidor (faltan{" "}
                {CHANNEL_SETUP[form.channel]} en el .env). Podés guardar igual: los avisos van a salir cuando
                se configure.
              </span>
            </p>
          )}
        </Panel>

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Panel title="Mensaje">
            <div className="space-y-5">
              {form.channel === "email" && (
                <Field
                  id={`${settings.stage}-subject`}
                  label="Asunto del email"
                  error={
                    wrongInSubject.length
                      ? `No existe ${wrongInSubject.map((w) => `{${w}}`).join(", ")}.`
                      : undefined
                  }
                >
                  {(aria) => (
                    <input
                      {...aria}
                      value={form.email_subject}
                      maxLength={150}
                      onChange={(e) => set("email_subject", e.target.value)}
                      className={inputClass(wrongInSubject.length > 0)}
                    />
                  )}
                </Field>
              )}
              <Field
                id={`${settings.stage}-message`}
                label="Texto del aviso"
                hint="Los datos entre llaves se reemplazan por los de cada factura."
                error={
                  wrongInMessage.length
                    ? `No existe ${wrongInMessage.map((w) => `{${w}}`).join(", ")}. Usá los de la lista.`
                    : undefined
                }
              >
                {(aria) => (
                  <textarea
                    {...aria}
                    ref={message}
                    rows={9}
                    maxLength={1600}
                    value={form.message}
                    onChange={(e) => set("message", e.target.value)}
                    className={inputClass(wrongInMessage.length > 0, "font-medium leading-relaxed")}
                  />
                )}
              </Field>
              {canManage && (
                <div>
                  <p className="text-xs font-bold text-ink">Agregar un dato</p>
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {data.placeholders.map((p) => (
                      <li key={p.name}>
                        <button
                          type="button"
                          onClick={() => insert(p.name)}
                          title={p.description}
                          className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-semibold text-rynx-primary hover:bg-rynx-soft/40"
                        >
                          {`{${p.name}}`}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Field
                id={`${settings.stage}-instructions`}
                label="Cómo pagar (opcional)"
                hint="Reemplaza a {instrucciones}: un link de pago, un CBU o los lugares de pago."
              >
                {(aria) => (
                  <textarea
                    {...aria}
                    rows={2}
                    maxLength={500}
                    value={form.instructions}
                    onChange={(e) => set("instructions", e.target.value)}
                    className={inputClass()}
                  />
                )}
              </Field>
              {form.channel === "whatsapp" && (
                <Field
                  id={`${settings.stage}-template`}
                  label="Plantilla aprobada de WhatsApp (opcional)"
                  hint={`Para escribirle primero a un deudor, WhatsApp exige una plantilla aprobada por Meta. Pegá acá el código que da Twilio (empieza con HX). Sus variables van en este orden: ${data.template_variables
                    .map((v, i) => `{{${i + 1}}} ${v}`)
                    .join(", ")}. Vacío: se manda el texto de arriba (sirve en el sandbox de prueba).`}
                >
                  {(aria) => (
                    <input
                      {...aria}
                      value={form.whatsapp_template_sid ?? ""}
                      maxLength={40}
                      spellCheck={false}
                      placeholder="HX…"
                      onChange={(e) => set("whatsapp_template_sid", e.target.value)}
                      className={inputClass(false, "font-mono")}
                    />
                  )}
                </Field>
              )}
            </div>
          </Panel>

          <aside aria-label="Así lo recibe el deudor" className="lg:sticky lg:top-8">
            <p className="mb-3 flex items-center gap-2 text-sm font-bold text-ink">
              {form.channel === "email" ? (
                <Mail aria-hidden className="size-4" />
              ) : (
                <MessageCircle aria-hidden className="size-4" />
              )}
              Así lo recibe el deudor
            </p>
            {form.channel === "email" ? (
              <div className="overflow-hidden rounded-2xl border border-gray-300 bg-white shadow-sm">
                <p className="border-b border-line bg-sunken/60 px-4 py-3 text-sm font-bold">
                  {renderSample(form.email_subject, values) || "(sin asunto)"}
                </p>
                <p className="px-4 py-4 text-sm leading-relaxed whitespace-pre-line">{preview}</p>
              </div>
            ) : (
              <div className="rounded-2xl bg-[#e9e3da] p-4">
                <p className="max-w-[92%] rounded-2xl rounded-tl-none bg-white px-4 py-3 text-sm leading-relaxed whitespace-pre-line shadow-sm">
                  {form.whatsapp_template_sid?.trim()
                    ? "Se manda la plantilla aprobada (su texto lo define la plantilla en Twilio)."
                    : preview}
                </p>
              </div>
            )}
            <p className="mt-2 text-xs text-muted">Con datos de ejemplo.</p>
          </aside>
        </div>
      </fieldset>
    </form>
  );
}
