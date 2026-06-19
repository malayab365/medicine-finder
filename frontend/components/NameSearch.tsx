"use client";

import { useState } from "react";

import AdverseEvents from "@/components/AdverseEvents";
import { DisclaimerFooter, ErrorBox } from "@/components/Disclaimer";
import LabelCard from "@/components/LabelCard";
import { ApiError, searchName } from "@/lib/api";
import type { NameSearchResponse } from "@/types";

export default function NameSearch() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<NameSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await searchName(q));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <form onSubmit={onSubmit} className="flex gap-2" autoComplete="off">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. ibuprofen"
          maxLength={200}
          required
          className="flex-1 rounded border border-gray-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-60"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error ? <ErrorBox title="Couldn’t complete the search.">{error}</ErrorBox> : null}

      {result ? (
        <div>
          <LabelCard
            heading={result.matched_name || result.query}
            rxcui={result.rxcui}
            label={result.label}
            fallback={`No drug label found for "${
              result.matched_name || result.query
            }". Try a different name or spelling.`}
          />
          <AdverseEvents events={result.adverse_events} />
          <DisclaimerFooter text={result.disclaimer} />
        </div>
      ) : null}
    </section>
  );
}
