import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { HealthResponse, PlaceResult } from "../lib/types";
import { useUiStore } from "../stores/ui";

type Props = {
  onSelect: (place: PlaceResult) => void;
  health?: HealthResponse;
};

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [delayMs, value]);
  return debounced;
}

export function SearchBox({ onSelect, health }: Props) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 300);
  const viewport = useUiStore((state) => state.viewport);
  const hosted = health?.provider_mode === "hosted";
  const search = useQuery({
    queryKey: ["search", debouncedQuery, viewport],
    queryFn: () => api.search(debouncedQuery, viewport ?? undefined),
    enabled: debouncedQuery.trim().length >= 2,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const errorMessage = search.error instanceof Error ? search.error.message : "";
  const quota = /quota|rate limit/i.test(errorMessage);

  return (
    <section className="panel">
      <h2>Find a place</h2>
      <input
        type="search"
        value={query}
        placeholder="Town, park, campground, fuel…"
        aria-label="Search places"
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="search-results" style={{ marginTop: "0.75rem" }}>
        {search.data?.results.map((place) => (
          <button key={place.id} type="button" onClick={() => onSelect(place)}>
            <span>
              <strong>{place.name}</strong>
              <div className="muted">{place.feature_type}</div>
            </span>
            <span className="muted">{place.score.toFixed(2)}</span>
          </button>
        ))}
        {search.isFetching ? (
          <p className="muted">{hosted ? "Searching Photon…" : "Searching local index…"}</p>
        ) : null}
        {search.data && search.data.results.length === 0 && !search.isFetching ? (
          <p className="muted">{hosted ? "No matching places." : "No local matches."}</p>
        ) : null}
        {search.error ? (
          <p className="error">
            {quota
              ? "Search quota or rate limit reached. Try again in a minute."
              : hosted
                ? "Photon search is temporarily unavailable."
                : errorMessage || "Search failed."}
          </p>
        ) : null}
      </div>
    </section>
  );
}
