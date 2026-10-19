"use client";

/**
 * "Generar casos": agrupa las facturas vencidas que todavía no están en un caso,
 * uno por deudor (POST /cases/generate). Si el deudor ya tiene un caso
 * pendiente, las facturas se suman a ese caso en vez de crear otro.
 *
 * Se muestra en la lista de facturas y al terminar una carga.
 */
import { CheckCircle2 } from "lucide-react";
import Link from "next/link";

import { Button, QueryError, buttonClass } from "@/components/ui";
import { useGenerateCases, useUnassignedOverdueCount } from "@/features/invoices";
import { count } from "@/lib/format";
import type { GenerationResult } from "@/lib/types";

/** El resultado contado en palabras. */
export function generationSummary(result: GenerationResult): string {
  if (result.invoices_assigned === 0) {
    return "No había facturas vencidas sin caso: no se cambió nada.";
  }
  const where: string[] = [];
  if (result.cases_created > 0) {
    where.push(count(result.cases_created, "caso nuevo", "casos nuevos"));
  }
  if (result.cases_updated > 0) {
    where.push(
      count(result.cases_updated, "caso pendiente que ya existía", "casos pendientes que ya existían"),
    );
  }
  const verb = result.invoices_assigned === 1 ? "Se agrupó" : "Se agruparon";
  return `${verb} ${count(result.invoices_assigned, "factura", "facturas")} en ${where.join(" y ")}.`;
}

export function GenerateCases({ canOperate }: { canOperate: boolean }) {
  const waiting = useUnassignedOverdueCount();
  const generate = useGenerateCases();

  if (generate.isSuccess) {
    return (
      <div
        role="status"
        className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border border-status-agreement/30 bg-status-agreement/5 px-5 py-4"
      >
        <CheckCircle2 aria-hidden className="size-5 shrink-0 text-status-agreement" />
        <p className="flex-1 text-sm">{generationSummary(generate.data)}</p>
        {generate.data.invoices_assigned > 0 && (
          <Link href="/cases" className={buttonClass("secondary")}>
            Ver casos
          </Link>
        )}
      </div>
    );
  }

  if (waiting.isError) return <QueryError error={waiting.error} retry={waiting.refetch} />;
  if (!waiting.isSuccess || waiting.data === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border border-petrol/25 bg-petrol-soft px-5 py-4">
      <div className="min-w-60 flex-1">
        <p className="font-semibold">
          {count(waiting.data, "factura vencida todavía no está", "facturas vencidas todavía no están")}{" "}
          en un caso
        </p>
        <p className="mt-0.5 text-sm text-muted">
          {canOperate
            ? "Al generar los casos se agrupan por deudor y aparecen en Casos."
            : "Las agrupa en casos alguien con rol de operador o administración."}
        </p>
      </div>
      {canOperate && (
        <Button loading={generate.isPending} onClick={() => generate.mutate()}>
          Generar casos
        </Button>
      )}
      {generate.isError && (
        <div className="basis-full">
          <QueryError error={generate.error} retry={() => generate.mutate()} />
        </div>
      )}
    </div>
  );
}
