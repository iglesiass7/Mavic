"use client";

import { ArrowLeft, Check, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { OfferDetails } from "@/components/OfferDetails";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, Fact, LoadingState, Panel, QueryError, cx } from "@/components/ui";
import { useCase, useCaseConversations, useCaseOffers } from "@/features/cases";
import {
  formatDate,
  formatDateTime,
  formatDays,
  formatDuration,
  formatMoney,
} from "@/lib/format";
import { CALL_RESULT_LABEL, offerLabel } from "@/lib/labels";
import type { CaseDetail, Conversation } from "@/lib/types";

// Celdas de la tabla de facturas: el borde de la primera y la última columna
// visibles queda alineado con el título del panel (que tiene px-5).
const CELL = "px-3 py-2.5 first:pl-5 last:pr-5 sm:px-5 max-sm:[&:nth-child(2)]:pl-5";

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const detail = useCase(caseId);

  return (
    <>
      <Link href="/cases" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft aria-hidden className="size-4" /> Casos
      </Link>

      {detail.isPending && <LoadingState label="Cargando el caso…" />}
      {detail.isError && (
        <div className="mt-4">
          <QueryError error={detail.error} retry={detail.refetch} />
        </div>
      )}
      {detail.isSuccess && <CaseView detail={detail.data} />}
    </>
  );
}

function CaseView({ detail }: { detail: CaseDetail }) {
  return (
    <>
      <header className="mt-3 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{detail.debtor.name}</h1>
          <p className="mt-1 text-sm text-muted">Caso {detail.number}</p>
        </div>
        <StatusBadge status={detail.status} />
      </header>

      {/* En celular la ficha de ofertas va primero: es lo que más se consulta. */}
      <div className="mt-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(300px,2fr)]">
        <div className="min-w-0 space-y-6">
          <Panel title="Deudor">
            <dl className="grid gap-4 sm:grid-cols-[auto_auto_minmax(0,1fr)] sm:gap-x-10">
              <Fact label="DNI">{detail.debtor.document_number}</Fact>
              <Fact label="Teléfono">{detail.debtor.phone}</Fact>
              <Fact label="Email">
                <span className="[overflow-wrap:anywhere]">{detail.debtor.email}</span>
              </Fact>
            </dl>
          </Panel>

          <Panel title={`Facturas (${detail.invoice_count})`}>
            <div className="-mx-5 -my-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-xs text-muted">
                  <tr>
                    <th scope="col" className={cx(CELL, "hidden font-medium sm:table-cell")}>
                      Número
                    </th>
                    <th scope="col" className={cx(CELL, "font-medium")}>Concepto</th>
                    <th scope="col" className={cx(CELL, "font-medium")}>Vencimiento</th>
                    <th scope="col" className={cx(CELL, "text-right font-medium")}>Monto</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.invoices.map((invoice) => (
                    <tr key={invoice.id} className="border-b border-line last:border-0">
                      <td className={cx(CELL, "hidden whitespace-nowrap text-muted sm:table-cell")}>
                        {invoice.external_id}
                      </td>
                      <td className={CELL}>
                        {invoice.description}
                        {/* En celular no entra la columna "Número": va debajo del concepto. */}
                        <span className="block text-xs text-muted sm:hidden">{invoice.external_id}</span>
                      </td>
                      <td className={cx(CELL, "whitespace-nowrap")}>{formatDate(invoice.due_date)}</td>
                      <td className={cx(CELL, "text-right whitespace-nowrap")}>
                        {formatMoney(invoice.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <CallsPanel caseId={detail.id} />
        </div>

        <OfferSheet detail={detail} />
      </div>
    </>
  );
}

// ---------------------------------------------------------------- ofertas

function OfferSheet({ detail }: { detail: CaseDetail }) {
  const offers = useCaseOffers(detail.id);

  return (
    <aside
      aria-labelledby="offer-sheet-title"
      className="order-first rounded-lg border border-petrol/25 bg-petrol-soft p-5 lg:sticky lg:top-8 lg:order-none"
    >
      <p className="text-sm text-muted">Debe</p>
      <p className="text-4xl font-bold tracking-tight">{formatMoney(detail.total_amount)}</p>
      <p className="mt-1 text-sm text-muted">
        Vencida desde el {formatDate(detail.oldest_due_date)} ({formatDays(detail.debt_age_days)})
      </p>

      <h2 id="offer-sheet-title" className="mt-6 border-t border-petrol/20 pt-5 font-semibold">
        Lo que el agente puede ofrecer hoy
      </h2>

      {offers.isPending && <LoadingState label="Calculando ofertas…" />}
      {offers.isError && <QueryError error={offers.error} retry={offers.refetch} />}
      {offers.isSuccess && <OfferDetails offers={offers.data} />}
    </aside>
  );
}

// ---------------------------------------------------------------- llamadas

function CallsPanel({ caseId }: { caseId: string }) {
  const calls = useCaseConversations(caseId);

  return (
    <Panel title="Llamadas del agente">
      {calls.isPending && <LoadingState label="Cargando llamadas…" />}
      {calls.isError && <QueryError error={calls.error} retry={calls.refetch} />}
      {calls.isSuccess && calls.data.length === 0 && (
        <EmptyState title="Todavía no hubo llamadas">
          Cuando el agente hable con el deudor, acá vas a ver qué se le ofreció y cómo terminó.
        </EmptyState>
      )}
      {calls.isSuccess && calls.data.length > 0 && (
        <ol className="space-y-4">
          {[...calls.data].reverse().map((call) => (
            <CallItem key={call.id} call={call} />
          ))}
        </ol>
      )}
    </Panel>
  );
}

function CallItem({ call }: { call: Conversation }) {
  return (
    <li className="rounded-md border border-line p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-semibold">
          {call.result ? CALL_RESULT_LABEL[call.result] : "Sin resultado registrado"}
        </p>
        <p className="text-xs text-muted">
          {formatDateTime(call.started_at)}
          {call.call_duration_secs !== null && ` · ${formatDuration(call.call_duration_secs)}`}
        </p>
      </div>

      <ul className="mt-3 space-y-1 text-sm">
        <li className="flex items-center gap-2">
          {call.identity_verified ? (
            <Check aria-hidden className="size-4 text-status-agreement" />
          ) : (
            <X aria-hidden className="size-4 text-status-disputed" />
          )}
          {call.identity_verified ? "Identidad verificada" : "Identidad no verificada"}
        </li>
        <li>
          <span className="text-muted">Ofertas presentadas: </span>
          {call.offered.length ? call.offered.map(offerLabel).join(" y ") : "ninguna"}
        </li>
        {call.agreement && (
          <li>
            <span className="text-muted">Acordó: </span>
            <span className="font-semibold">
              {offerLabel(call.agreement.offer_id)}, {formatMoney(call.agreement.total_amount)}
            </span>
          </li>
        )}
      </ul>

      {call.summary && <p className="mt-3 text-sm">{call.summary}</p>}

      {call.transcript && call.transcript.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-petrol">Ver la conversación</summary>
          <ol className="mt-3 space-y-2">
            {call.transcript.map((turn, index) => (
              <li key={index} className={turn.role === "agent" ? "pr-10" : "pl-10 text-right"}>
                <span className="block text-xs text-muted">
                  {turn.role === "agent" ? "Agente" : "Deudor"}
                </span>
                <span
                  className={`inline-block rounded-md px-3 py-2 ${turn.role === "agent" ? "bg-paper" : "bg-petrol-soft"}`}
                >
                  {turn.message}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </li>
  );
}
