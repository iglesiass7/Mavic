"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { RuleEditor } from "@/components/RuleEditor";
import { EmptyState, LoadingState, QueryError } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { useRules } from "@/features/rules";

export default function EditRulePage() {
  const { ruleId } = useParams<{ ruleId: string }>();
  const me = useMe();
  // El backend no tiene GET de una sola regla: se busca en la lista (son pocas).
  const rules = useRules();
  const rule = rules.data?.find((r) => r.id === ruleId);

  return (
    <>
      <Link href="/rules" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft aria-hidden className="size-4" /> Reglas
      </Link>
      <h1 className="mt-3 text-2xl font-bold tracking-tight">{rule ? rule.name : "Editar regla"}</h1>

      {rules.isPending && <LoadingState />}
      {rules.isError && <QueryError error={rules.error} retry={rules.refetch} />}
      {rules.isSuccess && !rule && (
        <div className="mt-6">
          <EmptyState title="La regla no existe">
            Volvé a <Link href="/rules" className="text-petrol underline">Reglas</Link>.
          </EmptyState>
        </div>
      )}
      {rule &&
        (can(me.data, "manage_rules") ? (
          // key: si cambia la regla, el formulario arranca de cero con sus datos.
          <RuleEditor key={rule.id} rule={rule} />
        ) : (
          <div className="mt-6">
            <EmptyState title="Tu rol no puede cambiar reglas">
              Lo hace alguien con rol de administración.
            </EmptyState>
          </div>
        ))}
    </>
  );
}
