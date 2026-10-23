"use client";

/**
 * Auditoría, con el diseño de Rynx: buscador, período y tipo de evento arriba,
 * la tabla abajo y el detalle de cada evento en el panel de la derecha.
 *
 * En Rynx esta pantalla mostraba eventos escritos a mano en el código. Acá cada
 * fila la dejó un cambio real (ADR-036) y la base no deja editarla ni borrarla.
 * Los filtros viven en la dirección (?q=...&tema=pagos&periodo=7).
 */
import { Bot, Download, Eye, Server, UserRound } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Sheet } from "@/components/Sheet";
import { Button, ErrorState, PageHeader, QueryError, cx, inputClass } from "@/components/ui";
import {
  ACTION_LABEL,
  AUDIT_PAGE_SIZE,
  CATEGORY_LABEL,
  LEVEL_LABEL,
  eventsToCsv,
  fetchAllEvents,
  useAuditEvents,
  type AuditFilters,
} from "@/features/audit";
import { errorMessage } from "@/lib/api";
import { businessDay, formatDateTime } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import type { AuditCategory, AuditEvent, AuditLevel } from "@/lib/types";

const CATEGORY_SLUG: Record<AuditCategory, string> = {
  settings: "configuracion",
  portfolio: "cartera",
  calls: "llamadas",
  payments: "pagos",
  reminders: "avisos",
};
const LEVEL_SLUG: Record<AuditLevel, string> = { critical: "critico", info: "operacion", system: "sistema" };
const PERIODS = [
  { value: "", label: "Todo" },
  { value: "1", label: "Hoy" },
  { value: "7", label: "Últimos 7 días" },
  { value: "30", label: "Últimos 30 días" },
  { value: "custom", label: "Elegir fechas" },
];

const LEVEL_STYLE: Record<AuditLevel, string> = {
  critical: "bg-status-disputed/10 text-status-disputed",
  info: "bg-status-contacted/10 text-status-contacted",
  system: "bg-sunken text-muted",
};

function bySlug<K extends string>(slugs: Record<K, string>, value: string | null): K | "" {
  const found = (Object.entries(slugs) as [K, string][]).find(([, slug]) => slug === value);
  return found ? found[0] : "";
}

function daysAgo(days: number): string {
  return businessDay(new Date(Date.now() - days * 86_400_000).toISOString());
}

/** Lee los filtros de la dirección. El período "7" se convierte en fechas (desde hace 6 días hasta hoy). */
function readFilters(params: URLSearchParams): AuditFilters & { period: string } {
  const period = params.get("periodo") ?? "";
  const page = Number(params.get("pagina"));
  const base = {
    search: params.get("q") ?? "",
    category: bySlug(CATEGORY_SLUG, params.get("tema")),
    level: bySlug(LEVEL_SLUG, params.get("nivel")),
    page: Number.isInteger(page) && page > 0 ? page : 1,
    period,
  };
  const date = (value: string | null) => (value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "");
  if (period === "custom")
    return { ...base, since: date(params.get("desde")), until: date(params.get("hasta")) };
  const days = Number(period);
  if ([1, 7, 30].includes(days)) return { ...base, since: daysAgo(days - 1), until: "" };
  return { ...base, period: "", since: "", until: "" };
}

const ACTOR_ICON = { user: UserRound, agent: Bot, system: Server };

function Details({ event }: { event: AuditEvent }) {
  const changes = event.details.cambios as Record<string, { antes: unknown; despues: unknown }> | undefined;
  const rest = Object.entries(event.details).filter(([key]) => key !== "cambios");
  const show = (value: unknown): string =>
    value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)
      ? "—"
      : Array.isArray(value)
        ? value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).join(", ")
        : typeof value === "boolean"
          ? value
            ? "Sí"
            : "No"
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value);

  return (
    <div className="space-y-6 text-sm">
      <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2">
        <dt className="text-muted">Cuándo</dt>
        <dd>{formatDateTime(event.occurred_at)}</dd>
        <dt className="text-muted">Quién</dt>
        <dd>{event.actor_name}</dd>
        <dt className="text-muted">Evento</dt>
        <dd>{ACTION_LABEL[event.action] ?? event.action}</dd>
        {event.subject_label && (
          <>
            <dt className="text-muted">Sobre</dt>
            <dd>{event.subject_label}</dd>
          </>
        )}
        <dt className="text-muted">Nivel</dt>
        <dd>{LEVEL_LABEL[event.level]}</dd>
      </dl>
      <p className="rounded-xl bg-sunken/60 px-4 py-3">{event.summary}</p>
      {changes && Object.keys(changes).length > 0 && (
        <table className="w-full text-left text-xs">
          <caption className="mb-2 text-left text-sm font-bold text-ink">Qué cambió</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 pr-2 font-semibold">
                Campo
              </th>
              <th scope="col" className="py-1 pr-2 font-semibold">
                Antes
              </th>
              <th scope="col" className="py-1 font-semibold">
                Después
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(changes).map(([field, change]) => (
              <tr key={field} className="border-t border-line align-top">
                <th scope="row" className="py-2 pr-2 font-semibold">
                  {field}
                </th>
                <td className="py-2 pr-2 whitespace-pre-line text-status-disputed">{show(change.antes)}</td>
                <td className="py-2 whitespace-pre-line text-status-agreement">{show(change.despues)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rest.length > 0 && (
        <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2 text-xs">
          {rest.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted">{key.replace(/_/g, " ")}</dt>
              <dd className="[overflow-wrap:anywhere]">{show(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="text-xs text-muted">
        Los eventos no se pueden editar ni borrar. Id: <span className="font-mono">{event.id}</span>
      </p>
    </div>
  );
}

function AuditScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readFilters(params);
  const events = useAuditEvents(filters);
  const [search, setSearch] = useState(filters.search);
  const typed = useDebounced(search);
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (!("pagina" in changes)) next.delete("pagina");
    const text = next.toString();
    router.push(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }

  useEffect(() => {
    if (typed.trim() !== filters.search.trim()) update({ q: typed.trim() });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando cambia lo escrito
  }, [typed]);

  async function download() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const all = await fetchAllEvents(filters);
      const blob = new Blob([eventsToCsv(all, formatDateTime)], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `auditoria-${businessDay(new Date().toISOString())}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setDownloadError(errorMessage(error));
    } finally {
      setDownloading(false);
    }
  }

  const columns: Column<AuditEvent>[] = [
    {
      key: "when",
      header: "Fecha y hora",
      className: "whitespace-nowrap tabular text-xs",
      cell: (e) => formatDateTime(e.occurred_at),
    },
    {
      key: "who",
      header: "Quién",
      className: "whitespace-nowrap",
      cell: (e) => {
        const Icon = ACTOR_ICON[e.actor_kind];
        return (
          <span className="inline-flex items-center gap-2 font-semibold">
            <Icon aria-hidden className="size-4 text-muted" />
            {e.actor_name}
          </span>
        );
      },
    },
    {
      key: "event",
      header: "Evento",
      className: "whitespace-nowrap",
      cell: (e) => (
        <span className="flex flex-col items-start gap-1">
          <span className="font-semibold">{ACTION_LABEL[e.action] ?? e.action}</span>
          <span
            className={cx("rounded-full px-2 py-0.5 text-[10px] font-bold uppercase", LEVEL_STYLE[e.level])}
          >
            {LEVEL_LABEL[e.level]}
          </span>
        </span>
      ),
    },
    { key: "subject", header: "Sobre", className: "text-xs", cell: (e) => e.subject_label ?? "—" },
    { key: "summary", header: "Detalle", className: "min-w-72 text-xs text-muted", cell: (e) => e.summary },
    {
      key: "open",
      header: "",
      className: "w-12",
      cell: (e) => (
        <button
          type="button"
          aria-label={`Ver el detalle: ${ACTION_LABEL[e.action] ?? e.action}, ${formatDateTime(e.occurred_at)}`}
          onClick={(click) => {
            click.stopPropagation();
            setOpen(e);
          }}
          className="rounded-lg p-1.5 text-muted hover:bg-sunken hover:text-ink"
        >
          <Eye aria-hidden className="size-4" />
        </button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Auditoría"
        subtitle="Quién hizo qué y cuándo. Los eventos no se pueden editar ni borrar."
        actions={
          <Button onClick={download} loading={downloading} disabled={!events.data?.total}>
            <Download aria-hidden className="size-4" /> Descargar registros
          </Button>
        }
      />
      {downloadError && (
        <div className="mb-4">
          <ErrorState message={downloadError} />
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-end gap-4">
        <label className="block">
          <span className="text-xs font-bold text-ink">Período</span>
          <select
            value={filters.period}
            onChange={(e) =>
              update({
                periodo: e.target.value,
                desde: e.target.value === "custom" ? daysAgo(6) : "",
                hasta: e.target.value === "custom" ? daysAgo(0) : "",
              })
            }
            className={inputClass(false, "mt-2 w-44")}
          >
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        {filters.period === "custom" && (
          <>
            <label className="block">
              <span className="text-xs font-bold text-ink">Desde</span>
              <input
                type="date"
                value={filters.since}
                onChange={(e) => update({ desde: e.target.value })}
                className={inputClass(false, "mt-2 w-40")}
              />
            </label>
            <label className="block">
              <span className="text-xs font-bold text-ink">Hasta</span>
              <input
                type="date"
                value={filters.until}
                onChange={(e) => update({ hasta: e.target.value })}
                className={inputClass(false, "mt-2 w-40")}
              />
            </label>
          </>
        )}
        <label className="block">
          <span className="text-xs font-bold text-ink">Tipo de evento</span>
          <select
            value={filters.category}
            onChange={(e) =>
              update({ tema: e.target.value ? CATEGORY_SLUG[e.target.value as AuditCategory] : "" })
            }
            className={inputClass(false, "mt-2 w-72")}
          >
            <option value="">Todos</option>
            {(Object.keys(CATEGORY_LABEL) as AuditCategory[]).map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-bold text-ink">Nivel</span>
          <select
            value={filters.level}
            onChange={(e) =>
              update({ nivel: e.target.value ? LEVEL_SLUG[e.target.value as AuditLevel] : "" })
            }
            className={inputClass(false, "mt-2 w-40")}
          >
            <option value="">Todos</option>
            {(Object.keys(LEVEL_LABEL) as AuditLevel[]).map((l) => (
              <option key={l} value={l}>
                {LEVEL_LABEL[l]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {events.isError ? (
        <QueryError error={events.error} retry={events.refetch} />
      ) : (
        <DataTable
          caption="Eventos de auditoría"
          columns={columns}
          rows={events.data?.items ?? []}
          rowKey={(e) => e.id}
          loading={events.isFetching}
          search={{
            value: search,
            onChange: setSearch,
            placeholder: "Buscar por persona, caso, regla o texto...",
          }}
          page={filters.page}
          pageSize={AUDIT_PAGE_SIZE}
          total={events.data?.total}
          onPage={(page) => update({ pagina: page > 1 ? String(page) : "" })}
          onRowClick={setOpen}
          empty="No hay eventos para los filtros elegidos."
        />
      )}

      <Sheet title="Detalle del evento" open={open !== null} onClose={() => setOpen(null)}>
        {open && <Details event={open} />}
      </Sheet>
    </>
  );
}

export default function AuditPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense>
      <AuditScreen />
    </Suspense>
  );
}
