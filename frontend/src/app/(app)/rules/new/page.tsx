"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { RuleEditor } from "@/components/RuleEditor";
import { EmptyState } from "@/components/ui";
import { can, useMe } from "@/features/auth";

export default function NewRulePage() {
  const me = useMe();
  return (
    <>
      <Link href="/rules" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft aria-hidden className="size-4" /> Reglas
      </Link>
      <h1 className="mt-3 text-2xl font-bold tracking-tight">Nueva regla</h1>
      {can(me.data, "manage_rules") ? (
        <RuleEditor />
      ) : (
        <div className="mt-6">
          <EmptyState title="Tu rol no puede crear reglas">Lo hace alguien con rol de administración.</EmptyState>
        </div>
      )}
    </>
  );
}
