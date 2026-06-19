import type { AdverseEvent } from "@/types";

export default function AdverseEvents({ events }: { events: AdverseEvent[] }) {
  if (!events || events.length === 0) return null;

  return (
    <section className="mt-4 border-t border-gray-200 pt-3">
      <h3 className="text-base font-semibold">Most-reported adverse events</h3>
      <p className="mb-2 text-xs text-gray-500">
        Raw counts from FDA adverse-event reports — not incidence rates, and not adjusted for how
        widely the drug is used.
      </p>
      <ol className="list-decimal space-y-1 pl-5">
        {events.map((e) => (
          <li key={e.term} className="flex max-w-sm justify-between gap-4">
            <span>{e.term}</span>
            <span className="tabular-nums text-gray-500">{e.count.toLocaleString()}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
