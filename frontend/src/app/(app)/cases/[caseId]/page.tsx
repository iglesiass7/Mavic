"use client";

/** Un caso en su propia página (para links directos). Es el mismo detalle que el panel de Casos. */
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { CaseDetail } from "@/components/CaseDetail";
import { Card, PageHeader } from "@/components/ui";

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  return (
    <>
      <PageHeader
        back={
          <Link
            href="/cases"
            className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-rynx-primary hover:underline"
          >
            <ArrowLeft aria-hidden className="size-4" /> Volver a casos
          </Link>
        }
        title="Detalle del caso"
      />
      <Card className="max-w-3xl p-6">
        <CaseDetail caseId={caseId} />
      </Card>
    </>
  );
}
