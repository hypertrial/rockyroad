import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, CalendarDays, Ellipsis, Map, Plus, Route, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { StatusNotice } from "../components/StatusNotice";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { TripSummary } from "../lib/types";

export function TripListPage() {
  const [name, setName] = useState("");
  const [pendingDelete, setPendingDelete] = useState<TripSummary | null>(null);
  const tripsHeadingRef = useRef<HTMLHeadingElement>(null);
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
  const remove = useMutation({
    mutationFn: (tripId: string) => api.deleteTrip(tripId),
    onSuccess: (_, tripId) => {
      queryClient.setQueryData<TripSummary[]>(["trips"], (current) =>
        current?.filter((trip) => trip.id !== tripId),
      );
      setPendingDelete(null);
      window.requestAnimationFrame(() => tripsHeadingRef.current?.focus());
    },
  });

  return (
    <main id="main-content" className="dashboard-page" tabIndex={-1}>
      <section className="dashboard-hero" aria-labelledby="dashboard-title">
        <div className="hero-copy">
          <span className="eyebrow">
            <Map aria-hidden="true" size={17} />
            {hosted ? "Canada + USA road-trip planner" : "Private offline road-trip planner"}
          </span>
          <h1 id="dashboard-title">Plan the long way around.</h1>
          <p>
            Build the route worth remembering—from the first coffee stop to the last stretch of open road.
            RockyRoad keeps every trip simple, visual, and ready to change.
          </p>
          <div className="hero-trust">
            <Route aria-hidden="true" size={18} />
            <span>
              {hosted
                ? "Live place search and routing across Canada and the USA."
                : "Maps, places, and routes stay on this machine."}
            </span>
          </div>
        </div>

        <form
          className="create-trip-card"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div>
            <span className="eyebrow">Start a new journey</span>
            <h2>Where are you headed?</h2>
          </div>
          <label htmlFor="trip-name">Trip name</label>
          <input
            id="trip-name"
            type="text"
            value={name}
            placeholder="Rockies to the coast"
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            autoComplete="off"
          />
          <button type="submit" className="button button-primary create-trip-button" disabled={create.isPending}>
            <Plus aria-hidden="true" size={19} />
            {create.isPending ? "Creating trip…" : "Create trip"}
          </button>
          {create.error ? <StatusNotice variant="error">{create.error.message}</StatusNotice> : null}
        </form>
      </section>

      <section className="trips-section" aria-labelledby="trips-heading">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Your journeys</span>
            <h2 id="trips-heading" ref={tripsHeadingRef} tabIndex={-1}>
              Saved trips
            </h2>
          </div>
          {trips.data?.length ? <span className="count-badge">{trips.data.length}</span> : null}
        </div>

        {trips.isLoading ? (
          <div className="trip-grid" aria-label="Loading trips">
            {[0, 1, 2].map((item) => (
              <div key={item} className="trip-card trip-card-skeleton" aria-hidden="true">
                <span className="skeleton skeleton-title" />
                <span className="skeleton skeleton-line" />
              </div>
            ))}
          </div>
        ) : null}
        {trips.error ? (
          <StatusNotice variant="error" actionLabel="Try again" onAction={() => void trips.refetch()}>
            {trips.error.message}
          </StatusNotice>
        ) : null}
        {trips.data?.length ? (
          <div className="trip-grid">
            {trips.data.map((trip, index) => (
              <article key={trip.id} className="trip-card">
                <div className="trip-card-topline">
                  <span className="trip-number" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <details className="trip-card-menu">
                    <summary className="icon-button" role="button" aria-label={`Actions for ${trip.name}`}>
                      <Ellipsis aria-hidden="true" size={20} />
                    </summary>
                    <div className="trip-card-menu-popover" aria-label={`Actions for ${trip.name}`}>
                      <button
                        type="button"
                        aria-label={`Delete ${trip.name}`}
                        onClick={() => {
                          remove.reset();
                          setPendingDelete(trip);
                        }}
                      >
                        <Trash2 aria-hidden="true" size={17} />
                        Delete trip
                      </button>
                    </div>
                  </details>
                </div>
                <Link to="/trips/$tripId" params={{ tripId: trip.id }} className="trip-card-link">
                  <h3>{trip.name}</h3>
                  <div className="trip-meta">
                    <span>
                      <Map aria-hidden="true" size={16} />
                      {trip.stop_count === 1 ? "1 stop" : `${trip.stop_count} stops`}
                    </span>
                    <span>
                      <CalendarDays aria-hidden="true" size={16} />
                      Updated {formatDate(trip.updated_at)}
                    </span>
                  </div>
                  <span className="trip-open">
                    Open trip <ArrowRight aria-hidden="true" size={18} />
                  </span>
                </Link>
              </article>
            ))}
          </div>
        ) : null}
        {trips.data && trips.data.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state-icon" aria-hidden="true">
              <Route size={28} />
            </span>
            <h3>Your first route starts here</h3>
            <p>Name a trip above, then add stops by searching or clicking the map.</p>
          </div>
        ) : null}
      </section>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete this trip?"
        description={
          pendingDelete
            ? `“${pendingDelete.name}” and all of its stops and saved route data will be permanently deleted.`
            : "This trip will be permanently deleted."
        }
        confirmLabel="Delete trip"
        busy={remove.isPending}
        error={remove.error?.message}
        onCancel={() => {
          remove.reset();
          setPendingDelete(null);
        }}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
        }}
      />
    </main>
  );
}
