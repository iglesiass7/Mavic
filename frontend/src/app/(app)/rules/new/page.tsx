"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { RuleEditor } from "@/components/RuleEditor";
import { EmptyState, PageHeader } from "@/components/ui";
import { can, useMe } from "@/features/auth";

const BACK = (
  <Link
    href="/rules?tramo=moroso"
    className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-rynx-primary hover:underline"
  >
    <ArrowLeft aria-hidden className="size-4" /> Volver a reglas
  </Link>
);

export default function NewRulePage() {
  const me = useMe();
  return (
    <>
      <PageHeader
        back={BACK}
        title="Nueva regla"
        subtitle="A qué casos se aplica y qué puede ofrecer el agente en esos casos."
      />
      {can(me.data, "manage_rules") ? (
        <RuleEditor />
      ) : (
        <div>
          <EmptyState title="Tu rol no puede crear reglas">Lo hace alguien con rol de administración.</EmptyState>
        </div>
      )}
    </>
  );
}
