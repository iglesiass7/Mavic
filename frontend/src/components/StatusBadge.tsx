import { CASE_STATUS_HINT, CASE_STATUS_LABEL } from "@/lib/labels";
import type { CaseStatus } from "@/lib/types";

const DOT_COLOR: Record<CaseStatus, string> = {
  pending: "bg-status-pending",
  contacted: "bg-status-contacted",
  agreement: "bg-status-agreement",
  disputed: "bg-status-disputed",
  escalated: "bg-status-escalated",
  closed: "bg-status-closed",
};

/** El estado del caso: un punto de color y el nombre. El color nunca va solo. */
export function StatusBadge({ status }: { status: CaseStatus }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm" title={CASE_STATUS_HINT[status]}>
      <span aria-hidden className={`size-2 shrink-0 rounded-full ${DOT_COLOR[status]}`} />
      {CASE_STATUS_LABEL[status]}
    </span>
  );
}
