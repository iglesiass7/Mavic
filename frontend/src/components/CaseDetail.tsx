"use client";

/**
 * Detalle de un caso, como el panel "Detalle del caso" de Rynx:
 *
 *   Caso #12                              PENDIENTE
 *   Deudor / DNI / Teléfono / Monto / Facturas
 *   [Llamar al deudor]  [Derivar a humano]
 *   Facturas asociadas (con buscador)
 *   Lo que ofrece el agente
 *   Acuerdos de pago
 *   Llamadas del agente  ->  Ver conversaciones
 *
 * Se usa en el panel lateral de la lista de casos y en /cases/{id}.
 */
import { CalendarCheck, Phone, Search, UserRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { can, useMe } from "@/features/auth";
import {
  isCallOngoing,
  useCase,
  useCaseConversations,
  useCaseOffers,
  useEscalateCase,
  useStartCall,
} from "@/features/cases";
import { formatDate, formatDateTime, formatDays, formatDuration, formatMoney } from "@/lib/format";
import {
  CALL_RESULT_LABEL,
  CALL_STATUS_LABEL,
  CASE_STATUS_LABEL,
  REVIEW_REASON_LABEL,
  offerLabel,
} from "@/lib/labels";
import type { CaseDetail as CaseDetailData, Conversation } from "@/lib/types";

import { OfferDetails } from "./OfferDetails";
import { STATUS_TEXT } from "./StatusBadge";
import { Button, EmptyState, Fact, LoadingState, QueryError, cx } from "./ui";

export function CaseDetail({ caseId }: { caseId: string }) {
  const detail = useCase(caseId);
  if (detail.isPending) return <LoadingState label="Cargando el caso…" />;
  if (detail.isError) return <QueryError error={detail.error} retry={detail.refetch} />;
  return <CaseDetailBody detail={detail.data} />;
}

function CaseDetailBody({ detail }: { detail: CaseDetailData }) {
  return (
    <div className="space-y-7">
      <div>
        <div className="flex items-baseline justify-between gap-3">
          <p className="font-display text-xl font-bold text-rynx-primary">Caso #{detail.number}</p>
          <p className={cx("font-display text-xl font-bold", STATUS_TEXT[detail.status])}>
            {CASE_STATUS_LABEL[detail.status]}
          </p>
        </div>
        <dl className="mt-3">
          <Fact label="Deudor">{detail.debtor.name}</Fact>
          <Fact label="DNI/CUIT/CUIL">{detail.debtor.document_number}</Fact>
          <Fact label="Teléfono">{detail.debtor.phone}</Fact>
          <Fact label="Email">
            <span className="[overflow-wrap:anywhere]">{detail.debtor.email}</span>
          </Fact>
          <Fact label="Monto">{formatMoney(detail.total_amount)}</Fact>
          <Fact label="Facturas">{detail.invoice_count}</Fact>
          <Fact label="Atraso">
            {formatDays(detail.debt_age_days)} (desde el {formatDate(detail.oldest_due_date)})
          </Fact>
        </dl>
        <CaseActions detail={detail} />
      </div>

      <InvoicesSection detail={detail} />

      <section aria-labelledby="offers-title">
        <h3 id="offers-title" className="mb-3 text-lg font-bold">
          Lo que ofrece el agente
        </h3>
        <OffersBox caseId={detail.id} />
      </section>

      <CallsSection detail={detail} />
    </div>
  );
}

// ---------------------------------------------------------------- acciones

function CaseActions({ detail }: { detail: CaseDetailData }) {
  const me = useMe();
  const start = useStartCall(detail.id);
  const escalate = useEscalateCase(detail.id);
  const calls = useCaseConversations(detail.id);
  const negotiable = detail.status === "pending" || detail.status === "contacted";
  if (!can(me.data, "operate_portfolio") || !negotiable) return null;
  const ongoing = calls.data?.some((call) => isCallOngoing(call)) ?? false;

  return (
    <div className="mt-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Button
          loading={start.isPending}
          disabled={ongoing || escalate.isPending}
          onClick={() => start.mutate()}
          title={ongoing ? "Ya hay una llamada en curso" : undefined}
        >
          <Phone aria-hidden className="size-4" />
          {ongoing ? "Llamada en curso" : "Llamar al deudor"}
        </Button>
        <Button
          variant="danger"
          loading={escalate.isPending}
          disabled={start.isPending}
          onClick={() => {
            if (window.confirm("¿Derivar el caso a una persona? El agente deja de llamarlo.")) {
              escalate.mutate();
            }
          }}
        >
          <UserRound aria-hidden className="size-4" />
          Derivar a humano
        </Button>
      </div>
      {start.isError && <QueryError error={start.error} retry={() => start.mutate()} />}
      {escalate.isError && <QueryError error={escalate.error} retry={() => escalate.mutate()} />}
      {start.isSuccess && (
        <p role="status" className="text-sm text-status-agreement">
          Llamando. El resultado aparece abajo cuando termine la llamada.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- facturas

function InvoicesSection({ detail }: { detail: CaseDetailData }) {
  const [search, setSearch] = useState("");
  const text = search.trim().toLowerCase();
  const invoices = detail.invoices.filter(
    (invoice) =>
      !text ||
      invoice.external_id.toLowerCase().includes(text) ||
      invoice.description.toLowerCase().includes(text),
  );
  return (
    <section aria-labelledby="invoices-title">
      <h3 id="invoices-title" className="mb-3 text-lg font-bold">
        Facturas asociadas
      </h3>
      {detail.invoices.length > 4 && (
        <label className="relative mb-3 block">
          <span className="sr-only">Buscar factura</span>
          <Search
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-gray-500"
          />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar..."
            className="w-full rounded-xl border border-gray-300 py-2.5 pr-3 pl-9 text-sm"
          />
        </label>
      )}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-xs">
          <thead className="bg-sunken text-left">
            <tr>
              <th scope="col" className="px-3 py-2.5 font-bold">Factura</th>
              <th scope="col" className="px-3 py-2.5 font-bold">Concepto</th>
              <th scope="col" className="px-3 py-2.5 text-right font-bold">Monto</th>
              <th scope="col" className="px-3 py-2.5 font-bold">Fecha Vto.</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice) => (
              <tr key={invoice.id} className="border-t border-line">
                <td className="px-3 py-2.5 whitespace-nowrap">{invoice.external_id}</td>
                <td className="px-3 py-2.5">{invoice.description}</td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">{formatMoney(invoice.amount)}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{formatDate(invoice.due_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- ofertas

function OffersBox({ caseId }: { caseId: string }) {
  const offers = useCaseOffers(caseId);
  if (offers.isPending) return <LoadingState label="Calculando ofertas…" />;
  if (offers.isError) return <QueryError error={offers.error} retry={offers.refetch} />;
  return (
    <div className="rounded-2xl bg-petrol-soft p-4">
      <OfferDetails offers={offers.data} />
    </div>
  );
}

// ---------------------------------------------------------------- acuerdos y llamadas

function CallsSection({ detail }: { detail: CaseDetailData }) {
  const calls = useCaseConversations(detail.id);
  const list = calls.data ? [...calls.data].reverse() : [];
  const agreements = list.filter((call) => call.agreement);

  return (
    <>
      <section aria-labelledby="agreements-title">
        <h3 id="agreements-title" className="mb-3 flex items-center gap-2 text-lg font-bold">
          <CalendarCheck aria-hidden className="size-5 text-rynx-primary" />
          Acuerdos de pago
        </h3>
        {calls.isSuccess && agreements.length === 0 && (
          <p className="rounded-2xl border border-dashed border-gray-300 px-4 py-4 text-sm text-muted">
            Todavía no se registraron acuerdos para este caso.
          </p>
        )}
        <ul className="space-y-2">
          {agreements.map((call) => (
            <li key={call.id} className="rounded-2xl border border-status-agreement/30 bg-status-agreement/5 px-4 py-3">
              <p className="font-semibold">
                {offerLabel(call.agreement!.offer_id)}: {formatMoney(call.agreement!.total_amount)}
              </p>
              {call.agreement!.installment_amount && (
                <p className="text-sm text-muted">
                  {call.agreement!.installment_count} cuotas de{" "}
                  {formatMoney(call.agreement!.installment_amount)}
                </p>
              )}
              <p className="text-xs text-muted">Acordado el {formatDateTime(call.agreement!.created_at)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="calls-title">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 id="calls-title" className="text-lg font-bold">
            Llamadas del agente
          </h3>
          {list.length > 0 && (
            <Link
              href={`/conversations?q=${encodeURIComponent(`#${detail.number}`)}`}
              className="rounded-xl bg-rynx-primary px-4 py-2 text-xs font-semibold text-white hover:bg-rynx-primary-hover"
            >
              Ver conversaciones
            </Link>
          )}
        </div>
        {calls.isPending && <LoadingState label="Cargando llamadas…" />}
        {calls.isError && <QueryError error={calls.error} retry={calls.refetch} />}
        {calls.isSuccess && list.length === 0 && (
          <EmptyState title="Todavía no hubo llamadas">
            Cuando el agente llame, acá vas a ver cómo terminó cada llamada.
          </EmptyState>
        )}
        <ol className="space-y-2">
          {list.map((call) => (
            <CallRow key={call.id} call={call} />
          ))}
        </ol>
      </section>
    </>
  );
}

function CallRow({ call }: { call: Conversation }) {
  return (
    <li className="rounded-2xl border border-line px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold">
          {call.result ? CALL_RESULT_LABEL[call.result] : CALL_STATUS_LABEL[call.status]}
        </p>
        <p className="text-xs text-muted">
          {formatDateTime(call.started_at)}
          {call.call_duration_secs !== null && ` · ${formatDuration(call.call_duration_secs)}`}
        </p>
      </div>
      {call.status === "FAILED" && call.failure_reason && (
        <p className="mt-1 text-sm text-status-disputed">No se pudo iniciar: {call.failure_reason}</p>
      )}
      {call.status === "NEEDS_REVIEW" && call.review_reason && (
        <p className="mt-1 text-sm text-status-escalated">
          Para revisar: {REVIEW_REASON_LABEL[call.review_reason] ?? call.review_reason}
        </p>
      )}
      {call.summary && <p className="mt-1 text-sm text-muted">{call.summary}</p>}
    </li>
  );
}
