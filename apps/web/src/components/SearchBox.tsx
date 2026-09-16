import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import type { PlaceResult } from "../lib/types";
import { useUiStore } from "../stores/ui";

type Props = {
  onSelect: (place: PlaceResult) => void;
};

export function SearchBox({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const viewport = useUiStore((state) => state.viewport);
  const search = useQuery({
    queryKey: ["search", query, viewport],
    queryFn: () => api.search(query, viewport ?? undefined),
    enabled: query.trim().length >= 2,
  });

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
        {search.isFetching ? <p className="muted">Searching local index…</p> : null}
        {search.data && search.data.results.length === 0 ? <p className="muted">No local matches.</p> : null}
      </div>
    </section>
  );
}
