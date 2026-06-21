"use client";

import { useEffect, useRef, useState } from "react";

import AdverseEvents from "@/components/AdverseEvents";
import { DisclaimerFooter, ErrorBox } from "@/components/Disclaimer";
import LabelCard from "@/components/LabelCard";
import { ApiError, searchName, suggestNames } from "@/lib/api";
import type { NameSearchResponse } from "@/types";

export default function NameSearch() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<NameSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // Set when a suggestion is picked so the resulting `query` change doesn't
  // immediately re-fetch suggestions for the value we just selected.
  const skipFetch = useRef(false);

  // Debounced suggestion fetch. All setState runs inside the timer (never
  // synchronously in the effect body) so it stays a deferred external sync.
  useEffect(() => {
    if (skipFetch.current) {
      skipFetch.current = false;
      return;
    }
    const q = query.trim();
    const handle = setTimeout(async () => {
      if (q.length < 2) {
        setSuggestions([]);
        setOpen(false);
        return;
      }
      try {
        const { suggestions } = await suggestNames(q);
        setSuggestions(suggestions);
        setActive(-1);
        setOpen(suggestions.length > 0);
      } catch {
        setSuggestions([]);
        setOpen(false);
      }
    }, 200);
    return () => clearTimeout(handle);
  }, [query]);

  async function runSearch(value: string) {
    const q = value.trim();
    if (!q) return;
    setOpen(false);
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

  function selectSuggestion(value: string) {
    skipFetch.current = true;
    setQuery(value);
    setSuggestions([]);
    setOpen(false);
    runSearch(value);
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    runSearch(query);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <section>
      <form onSubmit={onSubmit} className="flex gap-2" autoComplete="off">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            onFocus={() => suggestions.length > 0 && setOpen(true)}
            onBlur={() => setOpen(false)}
            placeholder="e.g. ibuprofen"
            maxLength={200}
            required
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-controls="name-suggestions"
            className="w-full rounded border border-gray-300 px-3 py-2"
          />
          {open ? (
            <ul
              id="name-suggestions"
              role="listbox"
              className="absolute z-10 mt-1 max-h-72 w-full overflow-auto rounded border border-gray-200 bg-white shadow-lg"
            >
              {suggestions.map((s, i) => (
                <li key={s} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    // Prevent the input's blur from firing before the click.
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectSuggestion(s)}
                    className={`block w-full px-3 py-2 text-left hover:bg-blue-50 ${
                      i === active ? "bg-blue-50" : ""
                    }`}
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
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
