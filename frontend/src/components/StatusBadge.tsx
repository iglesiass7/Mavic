import { CASE_STATUS_HINT, CASE_STATUS_LABEL } from "@/lib/labels";
import type { CaseStatus } from "@/lib/types";

import { cx } from "./ui";

/** Color de cada estado (los validados para daltonismo: ADR-033). */
export const STATUS_TEXT: Record<CaseStatus, string> = {
  pending: "text-status-pending",
  contacted: "text-status-contacted",
  agreement: "text-status-agreement",
  disputed: "text-status-disputed",
  escalated: "text-status-escalated",
  closed: "text-status-closed",
};

const PILL: Record<CaseStatus, string> = {
  pending: "bg-status-pending/10 text-status-pending",
  contacted: "bg-status-contacted/10 text-status-contacted",
  agreement: "bg-status-agreement/10 text-status-agreement",
  disputed: "bg-status-disputed/10 text-status-disputed",
  escalated: "bg-status-escalated/10 text-status-escalated",
  closed: "bg-status-closed/10 text-status-closed",
};

/** El estado del caso como etiqueta (la "pastilla" de Rynx). El color nunca va solo: lleva el nombre. */
export function StatusBadge({ status, className }: { status: CaseStatus; className?: string }) {
  return (
    <span
      title={CASE_STATUS_HINT[status]}
      className={cx(
        "inline-flex items-center rounded-full px-3 py-1 text-[11px] font-bold tracking-wider whitespace-nowrap uppercase",
        PILL[status],
        className,
      )}
    >
      {CASE_STATUS_LABEL[status]}
    </span>
  );
}
