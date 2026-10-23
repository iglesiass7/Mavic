"use client";

/**
 * Reglas de negocio, con el diseño de Rynx: una tabla con buscador, columnas
 * que se ordenan y páginas.
 *
 *   Regla | Descripción | Condiciones | Lo que ofrece | Estado | (Editar, Activar)
 *
 * Son pocas, así que se piden todas y se filtran y ordenan en el navegador.
 * En Mavic las reglas activas no se pueden pisar (a cada caso le toca una sola),
 * por eso no hay "prioridad" ni se arrastran filas como en Rynx.
 */
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button, PageHeader, QueryError, buttonClass, cx } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  describeConditions,
  describeTerms,
  sortRules,
  toRuleInput,
  useRules,
  useSaveRule,
  type RuleSort,
} from "@/features/rules";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/types";

function Lines({ lines }: { lines: { label: string; value: string }[] }) {
  return (
    <dl className="space-y-0.5 text-xs">
      {lines.map(({ label, value }) => (
        <div key={label}>
          <dt className="inline font-semibold text-ink">{label}: </dt>
          <dd className="inline text-muted">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Activar o desactivar desde la tabla: se guarda la misma regla con el otro estado. */
function ToggleRule({ rule }: { rule: Rule }) {
  const toggle = useSaveRule(rule.id);
  return (
    <div className="flex flex-col items-stretch gap-1">
      <Button
        variant="secondary"
        className="px-3 py-1.5 text-xs"
        loading={toggle.isPending}
        onClick={() => toggle.mutate({ ...toRuleInput(rule), is_active: !rule.is_active })}
      >
        {rule.is_active ? "Desactivar" : "Activar"}
      </Button>
      {toggle.isError && (
        <p role="alert" className="max-w-48 text-xs text-red-700">
          {errorMessage(toggle.error)}
        </p>
      )}
    </div>
  );
}

export default function RulesPage() {
  const me = useMe();
  const canManage = can(me.data, "manage_rules");
  const rules = useRules();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<RuleSort>("status");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const text = search.trim().toLowerCase();
  const matching = sortRules(
    (rules.data ?? []).filter(
      (rule) => !text || `${rule.name} ${rule.description}`.toLowerCase().includes(text),
    ),
    sort,
  );
  const rows = matching.slice((page - 1) * pageSize, page * pageSize);

  const columns: Column<Rule>[] = [
    {
      key: "name",
      header: "Regla",
      sortKey: "name",
      className: "min-w-40 font-bold",
      cell: (rule) => <span className={cx(!rule.is_active && "text-muted")}>{rule.name}</span>,
    },
    {
      key: "description",
      header: "Descripción",
      className: "min-w-40 max-w-64 text-xs text-muted",
      cell: (rule) => rule.description || "—",
    },
    {
      key: "conditions",
      header: "Se aplica a casos con",
      className: "min-w-44",
      cell: (rule) => <Lines lines={describeConditions(rule)} />,
    },
    {
      key: "terms",
      header: "El agente puede ofrecer",
      className: "min-w-48",
      cell: (rule) => <Lines lines={describeTerms(rule)} />,
    },
    {
      key: "status",
      header: "Estado",
      sortKey: "status",
      className: "whitespace-nowrap",
      cell: (rule) => (
        <span
          title={rule.is_active ? "El agente la usa" : "El agente no la usa"}
          className={cx("text-xs font-bold", rule.is_active ? "text-status-agreement" : "text-muted")}
        >
          {rule.is_active ? "Activa" : "Inactiva"}
        </span>
      ),
    },
  ];
  if (canManage) {
    columns.push({
      key: "actions",
      header: "Acciones",
      className: "whitespace-nowrap",
      cell: (rule) => (
        <div className="flex flex-col items-stretch gap-1.5">
          <Link href={`/rules/${rule.id}`} className={buttonClass("primary", "px-3 py-1.5 text-xs")}>
            Editar
          </Link>
          <ToggleRule rule={rule} />
        </div>
      ),
    });
  }

  return (
    <>
      <PageHeader
        title="Reglas de negocio"
        subtitle="Definí qué puede ofrecer el agente según la deuda, los días de atraso y la cantidad de facturas de cada caso."
      />

      <section aria-labelledby="negotiation-title">
        <div className="mb-5 max-w-3xl">
          <h2 id="negotiation-title" className="text-xl font-bold text-ink">
            Reglas de negociación
          </h2>
          <p className="mt-1 text-sm text-muted">
            Se usan con los casos de facturas vencidas. Las reglas activas no se pueden pisar: a cada caso le
            toca una sola. Si no le toca ninguna, el agente ofrece el monto completo sin descuento.
          </p>
        </div>

        {rules.isError ? (
          <QueryError error={rules.error} retry={rules.refetch} />
        ) : (
          <DataTable
            caption="Reglas de negociación"
            columns={columns}
            rows={rows}
            rowKey={(rule) => rule.id}
            loading={rules.isPending}
            search={{
              value: search,
              onChange: (value) => {
                setSearch(value);
                setPage(1);
              },
              placeholder: "Buscar por nombre o descripción...",
            }}
            toolbar={
              canManage && (
                <Link href="/rules/new" className={buttonClass("secondary")}>
                  <Plus aria-hidden className="size-4" /> Nueva regla
                </Link>
              )
            }
            sort={sort}
            onSort={(next) => setSort(next as RuleSort)}
            page={page}
            pageSize={pageSize}
            total={matching.length}
            onPage={setPage}
            onPageSize={(size) => {
              setPageSize(size);
              setPage(1);
            }}
            empty={
              text
                ? "Ninguna regla coincide con la búsqueda."
                : canManage
                  ? "Todavía no hay reglas. Creá la primera con “Nueva regla”. Mientras no haya ninguna, el agente ofrece el monto completo sin descuento."
                  : "Todavía no hay reglas. Las crea alguien con rol de administración."
            }
          />
        )}
        {!canManage && rules.isSuccess && rules.data.length > 0 && (
          <p className="mt-3 text-xs text-muted">Solo administración puede crear o cambiar reglas.</p>
        )}
      </section>
    </>
  );
}
