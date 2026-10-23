"use client";

/**
 * Acuerdos de pago del caso, con el seguimiento de cada cuota (ADR-037):
 *
 *   6 cuotas con interés · $ 134.400,54               ATRASADO
 *   Cobrado $ 22.400,09 de $ 134.400,54   ████░░░░░░░
 *   N°  Vence       Monto         Estado
 *   1   21/10/2026  $ 22.400,09   Pagada el 20/10  [Anular]
 *   2   21/11/2026  $ 22.400,09   Vencida          [Registrar pago]
 *
 * Las fechas salen del plazo de la regla (el agente no pacta fechas). Una
 * persona de la empresa registra cada pago; anular pide un motivo (auditoría).
 */
import { CalendarCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { can, useMe } from "@/features/auth";
import {
  AGREEMENT_STATUS_LABEL,
  useCaseAgreements,
  useRecordPayment,
  useUndoPayment,
} from "@/features/payments";
import { errorMessage } from "@/lib/api";
import { businessDay, formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { offerLabel } from "@/lib/labels";
import type { AgreementInstallment, AgreementStatus, AgreementTracking } from "@/lib/types";

import { Button, ErrorState, LoadingState, QueryError, cx, inputClass } from "./ui";

const STATUS_STYLE: Record<AgreementStatus, string> = {
  active: "bg-status-contacted/10 text-status-contacted",
  late: "bg-status-disputed/10 text-status-disputed",
  fulfilled: "bg-status-agreement/10 text-status-agreement",
};

function today(): string {
  return businessDay(new Date().toISOString());
}

function PayForm({
  caseId,
  agreement,
  installment,
  onDone,
}: {
  caseId: string;
  agreement: AgreementTracking;
  installment: AgreementInstallment;
  onDone: () => void;
}) {
  const record = useRecordPayment(caseId);
  const [paidOn, setPaidOn] = useState(today());
  const [note, setNote] = useState("");
  const id = `pay-${agreement.id}-${installment.number}`;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    record.mutate(
      { agreementId: agreement.id, number: installment.number, paidOn, note },
      { onSuccess: onDone },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-xl bg-sunken/60 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label htmlFor={`${id}-date`} className="block text-xs font-bold">
          Día en que pagó
          <input
            id={`${id}-date`}
            type="date"
            required
            value={paidOn}
            max={today()}
            min={businessDay(agreement.created_at)}
            onChange={(e) => setPaidOn(e.target.value)}
            className={inputClass(false, "mt-1 py-2")}
          />
        </label>
        <label htmlFor={`${id}-note`} className="block text-xs font-bold">
          Nota (opcional)
          <input
            id={`${id}-note`}
            value={note}
            maxLength={300}
            placeholder="Ej.: transferencia"
            onChange={(e) => setNote(e.target.value)}
            className={inputClass(false, "mt-1 py-2")}
          />
        </label>
      </div>
      {record.isError && <ErrorState message={errorMessage(record.error)} />}
      <div className="flex gap-2">
        <Button type="submit" loading={record.isPending} className="px-4 py-2 text-xs">
          Registrar pago de {formatMoney(installment.amount, agreement.currency)}
        </Button>
        <Button type="button" variant="ghost" className="px-3 py-2 text-xs" onClick={onDone}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

function UndoForm({
  caseId,
  agreement,
  installment,
  onDone,
}: {
  caseId: string;
  agreement: AgreementTracking;
  installment: AgreementInstallment;
  onDone: () => void;
}) {
  const undo = useUndoPayment(caseId);
  const [reason, setReason] = useState("");
  const id = `undo-${agreement.id}-${installment.number}`;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    undo.mutate({ agreementId: agreement.id, number: installment.number, reason }, { onSuccess: onDone });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-xl bg-sunken/60 p-3">
      <label htmlFor={id} className="block text-xs font-bold">
        ¿Por qué se anula? (queda en la auditoría)
        <input
          id={id}
          required
          value={reason}
          maxLength={300}
          placeholder="Ej.: se cargó en el caso equivocado"
          onChange={(e) => setReason(e.target.value)}
          className={inputClass(false, "mt-1 py-2")}
        />
      </label>
      {undo.isError && <ErrorState message={errorMessage(undo.error)} />}
      <div className="flex gap-2">
        <Button
          type="submit"
          variant="danger"
          loading={undo.isPending}
          disabled={!reason.trim()}
          className="px-4 py-2 text-xs"
        >
          Anular el pago
        </Button>
        <Button type="button" variant="ghost" className="px-3 py-2 text-xs" onClick={onDone}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

function InstallmentRow({
  caseId,
  agreement,
  installment,
  canOperate,
}: {
  caseId: string;
  agreement: AgreementTracking;
  installment: AgreementInstallment;
  canOperate: boolean;
}) {
  const [open, setOpen] = useState<"pay" | "undo" | null>(null);
  const paid = installment.paid_on !== null;
  const single = agreement.installment_count === 1;

  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="w-16 shrink-0 font-semibold">{single ? "Pago" : `Cuota ${installment.number}`}</span>
        <span className="w-36 shrink-0 whitespace-nowrap text-muted tabular">
          vence {formatDate(installment.due_date)}
        </span>
        <span className="w-28 shrink-0 font-medium tabular">
          {formatMoney(installment.amount, agreement.currency)}
        </span>
        <span
          className={cx(
            "flex-1 text-xs font-semibold",
            paid ? "text-status-agreement" : installment.overdue ? "text-status-disputed" : "text-muted",
          )}
          title={
            paid && installment.paid_recorded_at
              ? `Registrado el ${formatDateTime(installment.paid_recorded_at)}${installment.note ? ` · ${installment.note}` : ""}`
              : undefined
          }
        >
          {paid
            ? `Pagada el ${formatDate(installment.paid_on!)}`
            : installment.overdue
              ? "Vencida sin pagar"
              : "Pendiente"}
          {paid && installment.note && <span className="font-normal text-muted"> · {installment.note}</span>}
        </span>
        {canOperate && open === null && (
          <button
            type="button"
            onClick={() => setOpen(paid ? "undo" : "pay")}
            className={cx(
              "rounded-lg px-2.5 py-1 text-xs font-semibold",
              paid
                ? "text-muted hover:bg-sunken hover:text-ink"
                : "bg-rynx-primary text-white hover:bg-rynx-primary-hover",
            )}
          >
            {paid ? "Anular" : "Registrar pago"}
          </button>
        )}
      </div>
      {open === "pay" && (
        <div className="mt-2">
          <PayForm
            caseId={caseId}
            agreement={agreement}
            installment={installment}
            onDone={() => setOpen(null)}
          />
        </div>
      )}
      {open === "undo" && (
        <div className="mt-2">
          <UndoForm
            caseId={caseId}
            agreement={agreement}
            installment={installment}
            onDone={() => setOpen(null)}
          />
        </div>
      )}
    </li>
  );
}

function AgreementCard({
  caseId,
  agreement,
  canOperate,
}: {
  caseId: string;
  agreement: AgreementTracking;
  canOperate: boolean;
}) {
  const total = Number(agreement.total_amount);
  const paidShare = total > 0 ? Math.min(Number(agreement.paid_amount) / total, 1) : 0;
  return (
    <article className="rounded-2xl border border-line px-4 py-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">
            {offerLabel(agreement.offer_id)}: {formatMoney(agreement.total_amount, agreement.currency)}
          </p>
          <p className="text-xs text-muted">Acordado el {formatDateTime(agreement.created_at)}</p>
        </div>
        <span
          className={cx(
            "rounded-full px-3 py-1 text-[11px] font-bold tracking-wider uppercase",
            STATUS_STYLE[agreement.status],
          )}
        >
          {AGREEMENT_STATUS_LABEL[agreement.status]}
        </span>
      </header>

      <div className="mt-3">
        <p className="text-xs text-muted">
          Cobrado{" "}
          <span className="font-semibold text-ink">
            {formatMoney(agreement.paid_amount, agreement.currency)}
          </span>{" "}
          de {formatMoney(agreement.total_amount, agreement.currency)}
          {agreement.next_due_date && ` · próximo vencimiento ${formatDate(agreement.next_due_date)}`}
        </p>
        <div
          className="mt-1.5 h-2 overflow-hidden rounded-full bg-sunken"
          role="progressbar"
          aria-label="Cobrado del acuerdo"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(paidShare * 100)}
        >
          <div className="h-full rounded-full bg-status-agreement" style={{ width: `${paidShare * 100}%` }} />
        </div>
      </div>

      <ol className="mt-3 divide-y divide-line" aria-label="Cuotas">
        {agreement.installments.map((installment) => (
          <InstallmentRow
            key={installment.number}
            caseId={caseId}
            agreement={agreement}
            installment={installment}
            canOperate={canOperate}
          />
        ))}
      </ol>
    </article>
  );
}

export function AgreementsSection({ caseId }: { caseId: string }) {
  const me = useMe();
  const agreements = useCaseAgreements(caseId);
  const canOperate = can(me.data, "operate_portfolio");

  return (
    <section aria-labelledby="agreements-title">
      <h3 id="agreements-title" className="mb-3 flex items-center gap-2 text-lg font-bold">
        <CalendarCheck aria-hidden className="size-5 text-rynx-primary" />
        Acuerdos de pago
      </h3>
      {agreements.isPending && <LoadingState label="Cargando acuerdos…" />}
      {agreements.isError && <QueryError error={agreements.error} retry={agreements.refetch} />}
      {agreements.isSuccess && agreements.data.length === 0 && (
        <p className="rounded-2xl border border-dashed border-gray-300 px-4 py-4 text-sm text-muted">
          Todavía no se registraron acuerdos para este caso.
        </p>
      )}
      <div className="space-y-3">
        {agreements.data?.map((agreement) => (
          <AgreementCard key={agreement.id} caseId={caseId} agreement={agreement} canOperate={canOperate} />
        ))}
      </div>
    </section>
  );
}
