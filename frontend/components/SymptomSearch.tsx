"use client";

import { useState } from "react";

import { DisclaimerBanner, ErrorBox } from "@/components/Disclaimer";
import LabelCard from "@/components/LabelCard";
import { ApiError, searchSymptom } from "@/lib/api";
import type { SymptomSearchResponse } from "@/types";

export default function SymptomSearch() {
  const [symptoms, setSymptoms] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SymptomSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const s = symptoms.trim();
    if (!s) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await searchSymptom(s));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <form onSubmit={onSubmit} className="flex flex-col gap-2" autoComplete="off">
        <textarea
          value={symptoms}
          onChange={(e) => setSymptoms(e.target.value)}
          rows={3}
          placeholder="e.g. runny nose, sore throat, mild headache"
          maxLength={1000}
          required
          className="rounded border border-gray-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={loading}
          className="self-start rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-60"
        >
          {loading ? "Searching…" : "Find suggestions"}
        </button>
      </form>

      {error ? <ErrorBox title="Couldn’t complete the search.">{error}</ErrorBox> : null}

      {result ? (
        result.emergency ? (
          <div>
            <div className="my-4 rounded-md border-2 border-red-600 bg-red-100 px-5 py-4 font-semibold text-red-900">
              {result.message}
            </div>
            <DisclaimerBanner text={result.disclaimer} />
          </div>
        ) : (
          <div>
            <DisclaimerBanner text={result.disclaimer} />
            {result.candidates.length === 0 ? (
              <p>No suggestions found. Please consult a clinician.</p>
            ) : (
              result.candidates.map((c, i) => (
                <LabelCard
                  key={`${c.name}-${i}`}
                  heading={c.matched_name || c.name}
                  rxcui={c.rxcui}
                  label={c.label}
                  fallback={`Suggested: ${c.name}. No label details available.`}
                />
              ))
            )}
          </div>
        )
      ) : null}
    </section>
  );
}
