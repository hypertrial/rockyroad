import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";

export function TripListPage() {
  const [name, setName] = useState("New road trip");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const hosted = health.data?.provider_mode === "hosted";
  const trips = useQuery({ queryKey: ["trips"], queryFn: api.listTrips });
  const create = useMutation({
    mutationFn: () => api.createTrip(name.trim() || "New road trip"),
    onSuccess: async (trip) => {
      await queryClient.invalidateQueries({ queryKey: ["trips"] });
      await navigate({ to: "/trips/$tripId", params: { tripId: trip.id } });
    },
  });

  return (
    <main className="page">
      <section className="hero">
        <p className="muted">{hosted ? "Canada + USA planner" : "Local-first planner"}</p>
        <h1>{hosted ? "Plan the long way around." : "Pack the cooler. Leave the cloud."}</h1>
        <p>
          {hosted
            ? "RockyRoad plans Canada and USA road trips with OpenFreeMap tiles, Photon search, and OpenRouteService routing. Coordinates leave this machine through the local API."
            : "RockyRoad plans Canada and USA road trips from data on this machine: OSM places, a self-hosted Valhalla graph, and a local PMTiles map."}
        </p>
        <form
          className="create-row"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label className="sr-only" htmlFor="trip-name">
            Trip name
          </label>
          <input
            id="trip-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
          />
          <button type="submit" disabled={create.isPending}>
            Create trip
          </button>
        </form>
        {create.error ? <p className="error">{create.error.message}</p> : null}
      </section>
      {trips.isLoading ? <p>Loading trips…</p> : null}
      {trips.data?.length ? (
        <div className="trip-grid">
          {trips.data.map((trip) => (
            <Link key={trip.id} to="/trips/$tripId" params={{ tripId: trip.id }} className="trip-card">
              <h2>{trip.name}</h2>
              <p className="muted">
                {trip.stop_count} stops · {formatDate(trip.updated_at)}
              </p>
            </Link>
          ))}
        </div>
      ) : (
        <p className="empty" style={{ padding: "1rem" }}>
          No trips yet. Name one and start dropping stops on the map.
        </p>
      )}
    </main>
  );
}
