import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { LoaderCircle, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { HealthResponse, PlaceResult, ViewportBounds } from "../lib/types";
import { StatusNotice } from "./StatusNotice";

type Props = {
  onSelect: (place: PlaceResult) => void | Promise<void>;
  health?: HealthResponse;
  viewport: ViewportBounds | null;
  disabled?: boolean;
  editingName?: string | null;
};

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [delayMs, value]);
  return debounced;
}

function formatFeatureType(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function SearchBox({ onSelect, health, viewport, disabled = false, editingName }: Props) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 300);
  const hosted = health?.provider_mode === "hosted";
  const hasActiveQuery = query.trim().length >= 2;
  const search = useQuery({
    queryKey: ["search", debouncedQuery, viewport],
    queryFn: () => api.search(debouncedQuery, viewport ?? undefined),
    enabled: debouncedQuery.trim().length >= 2,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const errorMessage = search.error instanceof Error ? search.error.message : "";
  const quota = /quota|rate limit/i.test(errorMessage);
  const queryReady = hasActiveQuery && query.trim() === debouncedQuery.trim();
  const showResults = queryReady && !search.isPlaceholderData;

  return (
    <section className="planner-tool" aria-labelledby="search-heading">
      <div className="tool-heading">
        <span className="eyebrow">Add a waypoint</span>
        <h2 id="search-heading">{editingName ? `Move ${editingName}` : "Find a place"}</h2>
        <p className="muted">
          {editingName ? "Choose a new location for this stop." : "Search near the visible map or anywhere in Canada and the USA."}
        </p>
      </div>
      <div className="search-field-wrap">
        <Search aria-hidden="true" size={19} />
        <input
          type="search"
          value={query}
          placeholder="Town, park, campground, fuel…"
          aria-label="Search places"
          onChange={(event) => setQuery(event.target.value)}
          disabled={disabled}
          autoComplete="off"
        />
        {query ? (
          <button type="button" className="icon-button search-clear" aria-label="Clear search" onClick={() => setQuery("")}>
            <X aria-hidden="true" size={18} />
          </button>
        ) : null}
      </div>
      <div className="search-results" aria-live="polite">
        {showResults ? search.data?.results.map((place) => (
          <button key={place.id} type="button" disabled={disabled} onClick={() => void onSelect(place)}>
            <span className="search-result-copy">
              <strong>{place.name}</strong>
              <span className="muted">{formatFeatureType(place.feature_type)}</span>
            </span>
            <span className="search-result-coordinates">
              {place.lat.toFixed(2)}, {place.lon.toFixed(2)}
            </span>
          </button>
        )) : null}
        {queryReady && search.isFetching ? (
          <div className="search-loading" role="status">
            <span className="search-loading-label">
              <LoaderCircle className="spin" aria-hidden="true" size={18} />
              <span>{hosted ? "Searching places…" : "Searching the local index…"}</span>
            </span>
            <span className="search-result-skeleton" aria-hidden="true">
              <span className="skeleton skeleton-line" />
              <span className="skeleton skeleton-line" />
            </span>
          </div>
        ) : null}
        {!query.trim() ? <p className="search-prompt">Try a city, park, campground, viewpoint, or fuel stop.</p> : null}
        {showResults && search.data && search.data.results.length === 0 && !search.isFetching ? (
          <div className="search-empty">
            <strong>No places found</strong>
            <span>{hosted ? "Try a broader name or move the map closer." : "Try another name within your downloaded region."}</span>
          </div>
        ) : null}
        {queryReady && search.error ? (
          <StatusNotice variant="error" actionLabel="Try again" onAction={() => void search.refetch()}>
            {quota
              ? "Search quota or rate limit reached. Try again in a minute."
              : hosted
                ? "Photon search is temporarily unavailable."
                : errorMessage || "Search failed."}
          </StatusNotice>
        ) : null}
      </div>
    </section>
  );
}
