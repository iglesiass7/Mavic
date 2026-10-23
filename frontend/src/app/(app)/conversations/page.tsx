"use client";

/**
 * Conversaciones, con el diseño de Rynx: la lista de llamadas a la izquierda y
 * la conversación elegida a la derecha.
 *
 *   ┌─────────────────────┬──────────────────────────────────────────┐
 *   │ Conversaciones IA   │ Caso #12 / Ana Torres  [Descargar][Derivar]│
 *   │ [buscar]            ├──────────────────────────────────────────┤
 *   │ [fecha] [estado]    │   (fecha · resultado)                     │
 *   │ ┌ Caso #12 ACUERDO ┐│   Resumen                                 │
 *   │ └ Ana Torres  hoy  ┘│   deudor ▢                ▣ agente        │
 *   │ ┌ Caso #3  …       ┐│                                           │
 *   └─────────────────────┴──────────────────────────────────────────┘
 *
 * En Mavic cada tarjeta es una LLAMADA (no un caso): así se filtra por cómo
 * terminó cada una. Los filtros y la llamada elegida viven en la dirección
 * (?q=...&estado=acuerdo&llamada=<id>). En celular se ve una cosa por vez:
 * la lista, o la conversación con un botón para volver.
 */
import {
  ArrowLeft,
  CalendarDays,
  Download,
  ExternalLink,
  MessageSquare,
  Search,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { STATUS_TEXT } from "@/components/StatusBadge";
import { Button, LoadingState, QueryError, cx } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { isCallOngoing, useEscalateCase } from "@/features/cases";
import {
  CALLS_PAGE_SIZE,
  callFiltersQuery,
  callOutcome,
  formatSecs,
  readCallFilters,
  transcriptText,
  useCompanyCalls,
  type CallFilters,
} from "@/features/conversations";
import { businessDay, formatDate, formatDateTime, formatDuration, formatMoney } from "@/lib/format";
import { CALL_OUTCOME_FILTER_LABEL, REVIEW_REASON_LABEL, offerLabel } from "@/lib/labels";
import { useDebounced } from "@/lib/useDebounced";
import type { CallListItem, CallOutcomeFilter } from "@/lib/types";

const OUTCOMES = Object.keys(CALL_OUTCOME_FILTER_LABEL) as CallOutcomeFilter[];

// En celular hay una barra arriba (el logo y el botón del menú); en escritorio, no.
const FULL_HEIGHT = "h-[calc(100dvh-49px)] lg:h-dvh";

function ConversationsScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readCallFilters(params);
  const chosen = params.get("llamada");
  const calls = useCompanyCalls(filters);
  const [search, setSearch] = useState(filters.search);
  const typed = useDebounced(search);

  function go(next: CallFilters, callId: string | null) {
    const text = callFiltersQuery(next, callId);
    router.push(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }
  // Cambiar un filtro vuelve a la primera página y suelta la llamada elegida.
  const update = (changes: Partial<CallFilters>) => go({ ...filters, page: 1, ...changes }, null);

  // El buscador pide al backend cuando la persona deja de escribir.
  useEffect(() => {
    if (typed.trim() !== filters.search.trim()) update({ search: typed });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando cambia lo escrito
  }, [typed]);

  const items = calls.data?.items ?? [];
  // Sin una elegida, en escritorio se muestra la primera (como Rynx).
  const selected = chosen ? items.find((item) => item.call.id === chosen) : items[0];
  const pages = calls.data ? Math.max(1, Math.ceil(calls.data.total / CALLS_PAGE_SIZE)) : 1;
  const filtered = filters.search.trim() !== "" || filters.outcome !== "" || filters.day !== "";

  return (
    <div className={cx("flex overflow-hidden bg-white", FULL_HEIGHT)}>
      {/* ---------------------------------------------- la lista */}
      <section
        aria-label="Llamadas"
        className={cx(
          "w-full shrink-0 flex-col border-r border-gray-200 bg-white lg:flex lg:w-[400px]",
          chosen ? "hidden" : "flex",
        )}
      >
        <header className="space-y-5 border-b border-gray-300 px-6 pt-5 pb-5">
          <div className="space-y-1">
            <h1 className="font-display text-2xl font-black tracking-tight text-rynx-dark">
              Conversaciones IA
            </h1>
            <p className="text-sm font-medium text-ink/70">Lo que habló el agente en cada llamada.</p>
          </div>

          <label className="relative block">
            <span className="sr-only">Buscar llamadas</span>
            <Search aria-hidden className="absolute top-1/2 left-4 size-4 -translate-y-1/2 text-gray-400" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por N° de caso, deudor o DNI..."
              className="w-full rounded-xl border border-gray-200 bg-sunken/60 py-2.5 pr-3 pl-11 text-sm outline-none focus:ring-2 focus:ring-rynx-primary/20"
            />
          </label>

          <div className="flex gap-3">
            <label className="flex flex-1 flex-col">
              <span className="mx-2 mb-1 text-xs font-semibold text-ink">Fecha</span>
              <span className="flex h-10 items-center gap-2 rounded-xl border border-gray-300 bg-sunken/60 px-3">
                <CalendarDays aria-hidden className="size-3.5 shrink-0 text-gray-400" />
                <input
                  type="date"
                  value={filters.day}
                  onChange={(event) => update({ day: event.target.value })}
                  className="w-full min-w-0 bg-transparent text-xs font-medium text-rynx-dark outline-none"
                />
              </span>
            </label>
            <label className="flex flex-1 flex-col">
              <span className="mx-2 mb-1 text-xs font-semibold text-ink">Estado</span>
              <select
                value={filters.outcome}
                onChange={(event) =>
                  update({
                    outcome: event.target.value as CallOutcomeFilter | "",
                  })
                }
                className="h-10 w-full rounded-xl border border-gray-300 bg-sunken/60 px-3 text-xs font-medium text-rynx-dark outline-none"
              >
                <option value="">Todos los estados</option>
                {OUTCOMES.map((outcome) => (
                  <option key={outcome} value={outcome}>
                    {CALL_OUTCOME_FILTER_LABEL[outcome]}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>

        <div
          className="rynx-scroll flex-1 space-y-3 overflow-y-auto px-6 pt-4 pb-10"
          aria-busy={calls.isFetching}
        >
          {calls.isPending && <LoadingState label="Cargando llamadas…" />}
          {calls.isError && <QueryError error={calls.error} retry={calls.refetch} />}
          {calls.isSuccess && items.length === 0 && (
            <p className="mx-2 mt-2 text-sm text-muted">
              {filtered
                ? "Ninguna llamada coincide con los filtros."
                : "Todavía no hubo llamadas. Cuando el agente llame, las conversaciones aparecen acá."}
            </p>
          )}
          <ul className="space-y-3">
            {items.map((item) => (
              <li key={item.call.id}>
                <CallCard
                  item={item}
                  selected={item.call.id === selected?.call.id}
                  onSelect={() => go(filters, item.call.id)}
                />
              </li>
            ))}
          </ul>
          {calls.data && calls.data.total > CALLS_PAGE_SIZE && (
            <nav aria-label="Páginas de llamadas" className="flex items-center justify-between pt-2 text-xs">
              <Button
                variant="ghost"
                disabled={filters.page <= 1}
                onClick={() => go({ ...filters, page: filters.page - 1 }, null)}
              >
                Más nuevas
              </Button>
              <span className="text-muted">
                Página {filters.page} de {pages}
              </span>
              <Button
                variant="ghost"
                disabled={filters.page >= pages}
                onClick={() => go({ ...filters, page: filters.page + 1 }, null)}
              >
                Más viejas
              </Button>
            </nav>
          )}
        </div>
      </section>

      {/* ---------------------------------------------- la conversación */}
      <section
        aria-label="Conversación"
        className={cx("min-w-0 flex-1 flex-col bg-gray-200 lg:flex", chosen ? "flex" : "hidden")}
      >
        {selected ? (
          <ChatPane key={selected.call.id} item={selected} onBack={() => go(filters, null)} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center p-6 text-center text-rynx-dark/40">
            <MessageSquare aria-hidden className="size-16" />
            <p className="mt-4 font-bold">
              {chosen && calls.isSuccess
                ? "Esa llamada no está en esta lista."
                : "Elegí una llamada para ver la conversación."}
            </p>
            {chosen && (
              <button
                type="button"
                onClick={() => go(filters, null)}
                className="mt-3 text-sm font-semibold text-rynx-primary underline lg:hidden"
              >
                Volver a la lista
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- tarjeta de la lista

function CallCard({
  item,
  selected,
  onSelect,
}: {
  item: CallListItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const outcome = callOutcome(item.call);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cx(
        "flex w-full flex-col gap-3 rounded-2xl border p-5 text-left transition-colors",
        selected ? "border-rynx-primary bg-rynx-soft/40 shadow-sm" : "border-ink bg-white hover:bg-sunken/60",
      )}
    >
      <span className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-3">
          <MessageSquare aria-hidden strokeWidth={2.5} className="size-5 -scale-x-100 text-rynx-dark" />
          <span className="text-lg font-black tracking-tight text-rynx-dark">Caso #{item.case_number}</span>
        </span>
        <span className={cx("text-[11px] font-bold tracking-wider uppercase", STATUS_TEXT[outcome.tone])}>
          {outcome.label}
        </span>
      </span>
      <span className="flex items-center justify-between gap-3 text-[13px] text-rynx-dark/80">
        <span className="truncate font-bold">{item.debtor_name}</span>
        <span className="whitespace-nowrap tabular">{formatDate(businessDay(item.call.started_at))}</span>
      </span>
    </button>
  );
}

// ---------------------------------------------------------------- la conversación

function ChatPane({ item, onBack }: { item: CallListItem; onBack: () => void }) {
  const { call } = item;
  const outcome = callOutcome(call);
  const turns = (call.transcript ?? []).filter((turn) => turn.message?.trim());

  function download() {
    const blob = new Blob([transcriptText(item)], {
      type: "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `caso-${item.case_number}-${businessDay(call.started_at)}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <header className="z-10 flex flex-wrap items-center justify-between gap-4 bg-rynx-primary px-6 py-5 shadow-md">
        <div className="flex min-w-0 items-center gap-3 text-white">
          <button
            type="button"
            onClick={onBack}
            aria-label="Volver a la lista"
            className="rounded-lg p-1.5 hover:bg-white/10 lg:hidden"
          >
            <ArrowLeft aria-hidden className="size-5" />
          </button>
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-xl font-bold tracking-tight">
              Caso #{item.case_number}
              <Link
                href={`/cases?caso=${item.case_id}`}
                title="Ver el caso"
                aria-label={`Ver el caso #${item.case_number}`}
                className="rounded p-0.5 text-white/70 hover:text-white"
              >
                <ExternalLink aria-hidden className="size-4" />
              </Link>
            </h2>
            <p className="truncate text-xs font-medium text-white/80">{item.debtor_name}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={download}
            disabled={turns.length === 0 && !call.summary}
            className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-2.5 text-xs font-bold text-rynx-primary hover:bg-sunken disabled:opacity-50"
          >
            <Download aria-hidden className="size-4" /> Descargar chat
          </button>
          <EscalateButton item={item} />
        </div>
      </header>

      <div className="rynx-scroll flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-4xl space-y-5">
          <div className="flex justify-center">
            <p className="flex w-fit flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-full bg-ink px-4 py-1.5 text-[10px] font-bold tracking-widest text-white uppercase">
              <span>{formatDateTime(call.started_at)}</span>
              {call.call_duration_secs !== null && (
                <span className="border-l border-white/30 pl-3">
                  {formatDuration(call.call_duration_secs)}
                </span>
              )}
              <span className="border-l border-white/30 pl-3 text-rynx-accent">{outcome.label}</span>
            </p>
          </div>

          {call.status === "FAILED" && (
            <Notice tone="danger">
              No se pudo iniciar la llamada
              {call.failure_reason ? `: ${call.failure_reason}` : "."}
            </Notice>
          )}
          {call.status === "NEEDS_REVIEW" && (
            <Notice tone="warning">
              Para revisar:{" "}
              {call.review_reason
                ? (REVIEW_REASON_LABEL[call.review_reason] ?? call.review_reason)
                : "sin motivo."}{" "}
              El estado del caso no cambió.
            </Notice>
          )}
          {call.summary && (
            <p className="mx-auto max-w-3xl rounded-xl border border-rynx-soft bg-white px-4 py-3 text-xs text-rynx-dark shadow-sm">
              <span className="font-bold">Resumen: </span>
              {call.summary}
            </p>
          )}
          {call.agreement && (
            <p className="mx-auto max-w-3xl rounded-xl border border-status-agreement/30 bg-white px-4 py-3 text-xs text-rynx-dark shadow-sm">
              <span className="font-bold">Acuerdo: </span>
              {offerLabel(call.agreement.offer_id)},{" "}
              {formatMoney(call.agreement.total_amount, call.agreement.currency)}
              {call.agreement.installment_amount &&
                ` en ${call.agreement.installment_count} cuotas de ${formatMoney(call.agreement.installment_amount, call.agreement.currency)}`}
              .
            </p>
          )}

          {turns.length > 0 ? (
            <ol className="space-y-4" aria-label="Transcripción">
              {turns.map((turn, index) => (
                <ChatBubble
                  key={index}
                  fromAgent={turn.role === "agent"}
                  text={turn.message ?? ""}
                  time={turn.time_in_call_secs === null ? null : formatSecs(turn.time_in_call_secs)}
                />
              ))}
            </ol>
          ) : (
            <p className="rounded-2xl border border-dashed border-gray-300 bg-white/80 px-4 py-8 text-center text-sm font-medium text-muted">
              {isCallOngoing(call)
                ? "La llamada está en curso. La conversación aparece acá cuando termine (se actualiza sola)."
                : "Esta llamada no tiene transcripción."}
            </p>
          )}
        </div>
      </div>
    </>
  );
}

function ChatBubble({ fromAgent, text, time }: { fromAgent: boolean; text: string; time: string | null }) {
  return (
    <li className={cx("flex w-full", fromAgent ? "justify-end" : "justify-start")}>
      <div
        className={cx(
          "max-w-[80%] rounded-3xl p-4 text-sm font-medium shadow-sm sm:max-w-[70%]",
          fromAgent
            ? "rounded-tr-none bg-rynx-primary text-white"
            : "rounded-tl-none border border-gray-300 bg-white text-ink",
        )}
      >
        <p className="sr-only">{fromAgent ? "Agente:" : "Deudor:"}</p>
        <p className="leading-relaxed whitespace-pre-line">{text}</p>
        {time && (
          <p
            className={cx(
              "mt-2 text-right text-[10px] font-medium",
              fromAgent ? "text-white/80" : "text-gray-500",
            )}
          >
            {time}
          </p>
        )}
      </div>
    </li>
  );
}

function Notice({ tone, children }: { tone: "danger" | "warning"; children: ReactNode }) {
  return (
    <p
      className={cx(
        "mx-auto flex max-w-3xl items-start gap-2 rounded-xl border bg-white px-4 py-3 text-xs shadow-sm",
        tone === "danger"
          ? "border-red-200 text-red-700"
          : "border-status-escalated/30 text-status-escalated",
      )}
    >
      <TriangleAlert aria-hidden className="mt-px size-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

/** "Derivar a humano": solo si el rol puede operar y el caso todavía se negocia. */
function EscalateButton({ item }: { item: CallListItem }) {
  const me = useMe();
  const escalate = useEscalateCase(item.case_id);
  const negotiable = item.case_status === "pending" || item.case_status === "contacted";
  if (!can(me.data, "operate_portfolio") || !negotiable) return null;
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant="danger"
        loading={escalate.isPending}
        className="px-5 text-xs font-bold"
        onClick={() => {
          if (
            window.confirm(`¿Derivar el caso #${item.case_number} a una persona? El agente deja de llamarlo.`)
          ) {
            escalate.mutate();
          }
        }}
      >
        <UserRound aria-hidden className="size-4" /> Derivar a humano
      </Button>
      {escalate.isError && (
        <p role="alert" className="text-xs text-white">
          No se pudo derivar. Probá de nuevo.
        </p>
      )}
    </div>
  );
}

export default function ConversationsPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense>
      <ConversationsScreen />
    </Suspense>
  );
}
