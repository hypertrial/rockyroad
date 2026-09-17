import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { Directions } from "../components/Directions";
import { MapView } from "../components/MapView";
import { RouteOptions } from "../components/RouteOptions";
import { SearchBox } from "../components/SearchBox";
import { StopList } from "../components/StopList";
import { api, formatRoutingError } from "../lib/api";
import { formatDistance, formatDuration } from "../lib/format";
import { coverageHint, pointInExtract } from "../lib/mapCamera";
import { shouldPersistTripName } from "../lib/tripName";
import type { PlaceResult, Stop } from "../lib/types";
import { tripRoute } from "../router";
import { useUiStore } from "../stores/ui";

export function PlannerPage() {
  const { tripId } = useParams({ from: "/trips/$tripId" });
  const search = useSearch({ from: "/trips/$tripId" });
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const panel = useUiStore((state) => state.panel);
  const setPanel = useUiStore((state) => state.setPanel);
  const setSelectedStopId = useUiStore((state) => state.setSelectedStopId);
  const tripQuery = useQuery({ queryKey: ["trip", tripId], queryFn: () => api.getTrip(tripId) });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });

  useEffect(() => {
    if (search.panel) setPanel(search.panel);
    if (search.stop) setSelectedStopId(search.stop);
  }, [search.panel, search.stop, setPanel, setSelectedStopId]);

  const replaceStops = useMutation({
    mutationFn: (stops: Array<Pick<Stop, "name" | "lon" | "lat" | "place_id"> & { id?: string }>) =>
      api.replaceStops(tripId, stops),
    onSuccess: (trip) => queryClient.setQueryData(["trip", tripId], trip),
  });

  const updateTrip = useMutation({
    mutationFn: (name: string) => api.updateTrip(tripId, { name }),
    onSuccess: (trip) => queryClient.setQueryData(["trip", tripId], trip),
  });

  const routeTrip = useMutation({
    mutationFn: () => api.routeTrip(tripId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
      setPanel("directions");
    },
  });

  const optimizeTrip = useMutation({
    mutationFn: () => api.optimizeTrip(tripId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
      setPanel("directions");
    },
  });

  const trip = tripQuery.data;
  const [draftName, setDraftName] = useState(trip?.name ?? "");
  useEffect(() => {
    if (trip?.name) setDraftName(trip.name);
  }, [trip?.name]);
  const selected = useMemo(() => {
    const index = trip?.settings.selected_alternative ?? 0;
    return trip?.route?.alternatives[index] ?? trip?.route?.alternatives[0] ?? null;
  }, [trip]);
  const outsideExtract = Boolean(
    trip?.stops.some((stop) => !pointInExtract(stop.lon, stop.lat, health.data?.bounds ?? null)),
  );
  const coverage = coverageHint(health.data?.profile, health.data?.provider_mode);

  const addPlace = (place: PlaceResult) => {
    if (!trip) return;
    replaceStops.mutate([
      ...trip.stops.map((stop) => ({
        id: stop.id,
        name: stop.name,
        lon: stop.lon,
        lat: stop.lat,
        place_id: stop.place_id,
      })),
      { name: place.name, lon: place.lon, lat: place.lat, place_id: place.id },
    ]);
  };

  if (tripQuery.isLoading) {
    return <p className="page">Loading trip…</p>;
  }
  if (!trip) {
    return <p className="page error">Trip not found.</p>;
  }

  return (
    <div className="planner">
      <aside className="sidebar">
        <input
          type="text"
          value={draftName}
          aria-label="Trip name"
          onChange={(event) => setDraftName(event.target.value)}
          onBlur={() => {
            if (shouldPersistTripName(draftName, trip.name)) {
              updateTrip.mutate(draftName.trim());
            }
          }}
        />
        <div className="tabs" role="tablist">
          {(["search", "stops", "options", "directions"] as const).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={panel === item}
              onClick={() => {
                setPanel(item);
                void navigate({
                  from: tripRoute.fullPath,
                  search: (previous) => ({ ...previous, panel: item }),
                });
              }}
            >
              {item}
            </button>
          ))}
        </div>
        {panel === "search" ? <SearchBox onSelect={addPlace} health={health.data} /> : null}
        {panel === "stops" ? <StopList trip={trip} onChange={(stops) => replaceStops.mutate(stops)} /> : null}
        {panel === "options" ? <RouteOptions trip={trip} /> : null}
        {panel === "directions" ? <Directions trip={trip} /> : null}
        <div className="stack">
          <button
            type="button"
            onClick={() => routeTrip.mutate()}
            disabled={trip.stops.length < 2 || routeTrip.isPending || outsideExtract}
          >
            Build route
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => optimizeTrip.mutate()}
            disabled={trip.stops.length < 3 || optimizeTrip.isPending || outsideExtract}
          >
            Optimize stops
          </button>
        </div>
        {selected ? (
          <p className="muted">
            {formatDistance(selected.distance_m)} · {formatDuration(selected.duration_s)}
          </p>
        ) : (
          <p className="hint">Add at least two stops, then build a route.</p>
        )}
        {outsideExtract ? (
          <p className="error">
            Some stops are outside the current map coverage.{coverage ? ` ${coverage}` : ""}
          </p>
        ) : null}
        {routeTrip.error ? (
          <p className="error">
            {formatRoutingError(routeTrip.error.message, health.data?.profile, health.data?.provider_mode)}
          </p>
        ) : null}
        {optimizeTrip.error ? (
          <p className="error">
            {formatRoutingError(optimizeTrip.error.message, health.data?.profile, health.data?.provider_mode)}
          </p>
        ) : null}
      </aside>
      <MapView
        trip={trip}
        onAddStop={(lon, lat) =>
          replaceStops.mutate([
            ...trip.stops.map((stop) => ({
              id: stop.id,
              name: stop.name,
              lon: stop.lon,
              lat: stop.lat,
              place_id: stop.place_id,
            })),
            { name: `Stop ${trip.stops.length + 1}`, lon, lat, place_id: null },
          ])
        }
      />
    </div>
  );
}
