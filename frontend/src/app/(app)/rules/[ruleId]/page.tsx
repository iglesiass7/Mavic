"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { RuleEditor } from "@/components/RuleEditor";
import { EmptyState, LoadingState, PageHeader, QueryError } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import { useRules } from "@/features/rules";

const BACK = (
  <Link
    href="/rules"
    className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-rynx-primary hover:underline"
  >
    <ArrowLeft aria-hidden className="size-4" /> Volver a reglas
  </Link>
);

export default function EditRulePage() {
  const { ruleId } = useParams<{ ruleId: string }>();
  const me = useMe();
  // El backend no tiene GET de una sola regla: se busca en la lista (son pocas).
  const rules = useRules();
  const rule = rules.data?.find((r) => r.id === ruleId);

  return (
    <>
      <PageHeader back={BACK} title={rule ? rule.name : "Editar regla"} subtitle="Los cambios se usan desde la próxima llamada." />

      {rules.isPending && <LoadingState />}
      {rules.isError && <QueryError error={rules.error} retry={rules.refetch} />}
      {rules.isSuccess && !rule && (
        <div>
          <EmptyState title="La regla no existe">
            Volvé a <Link href="/rules" className="font-semibold text-rynx-primary underline">Reglas</Link>.
          </EmptyState>
        </div>
      )}
      {rule &&
        (can(me.data, "manage_rules") ? (
          // key: si cambia la regla, el formulario arranca de cero con sus datos.
          <RuleEditor key={rule.id} rule={rule} />
        ) : (
          <div>
            <EmptyState title="Tu rol no puede cambiar reglas">
              Lo hace alguien con rol de administración.
            </EmptyState>
          </div>
        ))}
    </>
  );
}
