/** Una regla contada en palabras: a qué casos se aplica y qué ofrece el agente. */
import { describeConditions, describeTerms } from "@/features/rules";
import type { Rule } from "@/lib/types";

function Lines({ title, lines }: { title: string; lines: { label: string; value: string }[] }) {
  return (
    <div>
      <p className="text-xs text-muted">{title}</p>
      <dl className="mt-1.5 space-y-1 text-sm">
        {lines.map(({ label, value }) => (
          <div key={label} className="flex gap-2">
            <dt className="w-24 shrink-0 text-muted">{label}</dt>
            <dd className="first-letter:uppercase">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function RuleSummary({ rule }: { rule: Rule }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <Lines title="Se aplica a casos con" lines={describeConditions(rule)} />
      <Lines title="El agente puede ofrecer" lines={describeTerms(rule)} />
    </div>
  );
}
