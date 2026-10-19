"use client";

import { Plus } from "lucide-react";
import Link from "next/link";

import { RuleSummary } from "@/components/RuleSummary";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  QueryError,
  buttonClass,
  cx,
} from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { toRuleInput, useRules, useSaveRule } from "@/features/rules";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/types";

function RuleRow({ rule, canManage }: { rule: Rule; canManage: boolean }) {
  // Activar o desactivar desde la lista: se guarda la misma regla con el otro estado.
  const toggle = useSaveRule(rule.id);
  return (
    <li className={cx("px-5 py-5", !rule.is_active && "bg-paper/60")}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        {/* basis-72: si no entran título y botones en una línea, los botones bajan. */}
        <div className="min-w-0 flex-1 basis-72">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className={cx("font-semibold", !rule.is_active && "text-muted")}>{rule.name}</h2>
            <span
              className={cx(
                "inline-flex items-center gap-1.5 text-xs",
                rule.is_active ? "text-status-agreement" : "text-muted",
              )}
            >
              <span
                aria-hidden
                className={cx("size-1.5 rounded-full", rule.is_active ? "bg-status-agreement" : "bg-muted")}
              />
              {rule.is_active ? "Activa" : "Inactiva: el agente no la usa"}
            </span>
          </div>
          {rule.description && <p className="mt-1 text-sm text-muted">{rule.description}</p>}
        </div>
        {canManage && (
          <div className="flex items-start gap-2">
            <Link href={`/rules/${rule.id}`} className={buttonClass("ghost")}>
              Editar
            </Link>
            <Button
              variant="secondary"
              loading={toggle.isPending}
              onClick={() => toggle.mutate({ ...toRuleInput(rule), is_active: !rule.is_active })}
            >
              {rule.is_active ? "Desactivar" : "Activar"}
            </Button>
          </div>
        )}
      </div>
      {toggle.isError && (
        <div className="mt-3">
          <ErrorState message={errorMessage(toggle.error)} />
        </div>
      )}
      <div className={cx("mt-4", !rule.is_active && "opacity-70")}>
        <RuleSummary rule={rule} />
      </div>
    </li>
  );
}

export default function RulesPage() {
  const me = useMe();
  const canManage = can(me.data, "manage_rules");
  const rules = useRules();
  // Primero las activas (las que usa el agente), después las inactivas.
  const sorted = [...(rules.data ?? [])].sort((a, b) => Number(b.is_active) - Number(a.is_active));

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight">Reglas de negociación</h1>
          <p className="mt-1 text-sm text-muted">
            Definen qué puede ofrecer el agente según la deuda, los días de atraso y la cantidad de
            facturas de cada caso. Las reglas activas no se pueden pisar: a cada caso le toca una
            sola. Si no le toca ninguna, el agente ofrece el monto completo sin descuento.
          </p>
        </div>
        {canManage && (
          <Link href="/rules/new" className={buttonClass()}>
            <Plus aria-hidden className="size-4" /> Nueva regla
          </Link>
        )}
      </div>

      <div className="mt-6">
        {rules.isPending && <LoadingState label="Cargando reglas…" />}
        {rules.isError && <QueryError error={rules.error} retry={rules.refetch} />}
        {rules.isSuccess && sorted.length === 0 && (
          <EmptyState title="Todavía no hay reglas">
            {canManage
              ? "Creá la primera con “Nueva regla”. Mientras no haya ninguna, el agente ofrece el monto completo sin descuento."
              : "Las crea alguien con rol de administración."}
          </EmptyState>
        )}
        {rules.isSuccess && sorted.length > 0 && (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {sorted.map((rule) => (
              <RuleRow key={rule.id} rule={rule} canManage={canManage} />
            ))}
          </ul>
        )}
        {!canManage && rules.isSuccess && sorted.length > 0 && (
          <p className="mt-3 text-xs text-muted">Solo administración puede crear o cambiar reglas.</p>
        )}
      </div>
    </>
  );
}
