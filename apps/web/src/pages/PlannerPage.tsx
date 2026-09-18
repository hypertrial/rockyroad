import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { ChevronDown, ChevronUp, LoaderCircle, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Directions } from "../components/Directions";
import { MapView } from "../components/MapView";
import { PlannerTabs, type PlannerPanel } from "../components/PlannerTabs";
import { RouteOptions } from "../components/RouteOptions";
import { SearchBox } from "../components/SearchBox";
import { StatusNotice } from "../components/StatusNotice";
import { StopList } from "../components/StopList";
import { useTripActions } from "../hooks/useTripActions";
import { api, formatRoutingError } from "../lib/api";
import { formatDistance, formatDuration } from "../lib/format";
import { coverageHint, pointInExtract } from "../lib/mapCamera";
import { restoreRemovedStop, toStopDrafts, withMovedStop } from "../lib/mapInteraction";
import { shouldPersistTripName } from "../lib/tripName";
import type { PlaceResult, Trip, ViewportBounds } from "../lib/types";
import { tripRoute } from "../router";

type PlannerNotice = {
  message: string;
  variant?: "info" | "success" | "error";
  actionLabel?: string;
  action?: () => void | Promise<void>;
};

export function PlannerPage() {
  const { tripId } = useParams({ from: "/trips/$tripId" });
  const search = useSearch({ from: "/trips/$tripId" });
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tripQuery = useQuery({ queryKey: ["trip", tripId], queryFn: () => api.getTrip(tripId) });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const actions = useTripActions(tripId);
  const [sheetExpanded, setSheetExpanded] = useState(true);
  const [editingStopId, setEditingStopId] = useState<string | null>(null);
  const [viewport, setViewport] = useState<ViewportBounds | null>(null);
  const [previewPlace, setPreviewPlace] = useState<PlaceResult | null>(null);
  const [notice, setNotice] = useState<PlannerNotice | null>(null);
  const [fitRouteNonce, setFitRouteNonce] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [draftName, setDraftName] = useState("");
  const skipNextBlurRef = useRef(false);
  const sheetToggleRef = useRef<HTMLButtonElement | null>(null);
  const trip = tripQuery.data;

  useEffect(() => {
    if (trip?.name) setDraftName(trip.name);
  }, [trip?.name]);

  useEffect(() => {
    if (!notice) return;
    const handle = window.setTimeout(() => setNotice(null), 7000);
    return () => window.clearTimeout(handle);
  }, [notice]);

  const activePanel: PlannerPanel = search.panel ?? (trip?.stops.length ? "stops" : "search");
  const selectedStopId = search.stop && trip?.stops.some((stop) => stop.id === search.stop) ? search.stop : null;
  const editingStop = editingStopId ? trip?.stops.find((stop) => stop.id === editingStopId) ?? null : null;

  const updatePlannerSearch = (patch: { panel?: PlannerPanel; stop?: string | undefined }) => {
    void navigate({
      from: tripRoute.fullPath,
      search: (previous) => ({ ...previous, ...patch }),
    });
  };

  const setPanel = (panel: PlannerPanel) => {
    updatePlannerSearch({ panel });
    setSheetExpanded(true);
  };

  const latestTrip = () => queryClient.getQueryData<Trip>(["trip", tripId]) ?? trip;

  const addOrReplacePlace = async (place: PlaceResult) => {
    const current = latestTrip();
    if (!current || actions.busy) return;
    const id = editingStopId ?? crypto.randomUUID();
    const next = editingStopId
      ? toStopDrafts(current.stops).map((stop) =>
          stop.id === editingStopId
            ? {
                ...stop,
                name: place.name,
                lon: place.lon,
                lat: place.lat,
                place_id: place.id,
                region: place.region ?? null,
              }
          : stop,
        )
      : [
          ...toStopDrafts(current.stops),
          { id, name: place.name, lon: place.lon, lat: place.lat, place_id: place.id, region: place.region ?? null },
        ];
    try {
      await actions.replaceStops(next);
      setEditingStopId(null);
      updatePlannerSearch({ panel: "stops", stop: id });
      setSheetExpanded(false);
      if (window.matchMedia("(max-width: 899px)").matches) {
        window.requestAnimationFrame(() => sheetToggleRef.current?.focus());
      }
      setNotice({
        message: editingStopId ? `${place.name} replaced the stop location.` : `${place.name} added to the trip.`,
        variant: "success",
      });
    } catch {
      setSheetExpanded(true);
    }
  };

  const addMapStop = async (lon: number, lat: number) => {
    const current = latestTrip();
    if (!current || actions.busy) return;
    const id = crypto.randomUUID();
    const stops = toStopDrafts(current.stops);
    try {
      await actions.replaceStops([
        ...stops,
        { id, name: `Stop ${stops.length + 1}`, lon, lat, place_id: null, region: null },
      ]);
      updatePlannerSearch({ panel: "stops", stop: id });
      setNotice({ message: `Stop ${stops.length + 1} added from the map.`, variant: "success" });
    } catch {
      setSheetExpanded(true);
    }
  };

  const moveMapStop = async (stopId: string, lon: number, lat: number) => {
    const current = latestTrip();
    if (!current || actions.busy) return;
    try {
      await actions.replaceStops(withMovedStop(toStopDrafts(current.stops), stopId, lon, lat));
    } catch {
      setNotice({ message: actions.stopError?.message ?? "The stop could not be moved.", variant: "error" });
    }
  };

  const removeStop = async (stopId: string) => {
    const current = latestTrip();
    if (!current || actions.busy) return;
    const index = current.stops.findIndex((stop) => stop.id === stopId);
    const removed = current.stops[index];
    if (!removed) return;
    const before = toStopDrafts(current.stops);
    const next = before.filter((stop) => stop.id !== stopId);
    try {
      await actions.replaceStops(next);
      if (selectedStopId === stopId) updatePlannerSearch({ stop: undefined });
      setNotice({
        message: `${removed.name} removed.`,
        variant: "info",
        actionLabel: "Undo",
        action: async () => {
          const latest = latestTrip();
          if (!latest) return;
          const restored = restoreRemovedStop(toStopDrafts(latest.stops), before[index], index);
          if (restored.length === latest.stops.length) return;
          try {
            await actions.replaceStops(restored);
            updatePlannerSearch({ panel: "stops", stop: stopId });
            setNotice({ message: `${removed.name} restored.`, variant: "success" });
          } catch {
            setNotice({ message: "The stop could not be restored.", variant: "error" });
          }
        },
      });
    } catch {
      // The shared action rolls the optimistic removal back and exposes the error below.
    }
  };

  const saveName = async () => {
    if (!trip || actions.busy || skipNextBlurRef.current) {
      skipNextBlurRef.current = false;
      return;
    }
    if (!shouldPersistTripName(draftName, trip.name)) {
      setDraftName(trip.name);
      return;
    }
    try {
      await actions.rename(draftName.trim());
    } catch {
      setDraftName(trip.name);
    }
  };

  if (tripQuery.isLoading) {
    return (
      <main id="main-content" className="planner-loading" aria-label="Loading trip" tabIndex={-1}>
        <div className="planner-loading-panel">
          <span className="skeleton skeleton-title" />
          <span className="skeleton skeleton-line" />
          <span className="skeleton skeleton-line" />
        </div>
        <div className="planner-loading-map" />
      </main>
    );
  }
  if (tripQuery.error) {
    return (
      <main id="main-content" className="planner-missing" tabIndex={-1}>
        <h1>Trip unavailable</h1>
        <StatusNotice variant="error" actionLabel="Try again" onAction={() => void tripQuery.refetch()}>
          {tripQuery.error.message}
        </StatusNotice>
        <Link to="/" className="button button-secondary">Back to trips</Link>
      </main>
    );
  }
  if (!trip) {
    return (
      <main id="main-content" className="planner-missing" tabIndex={-1}>
        <h1>Trip not found</h1>
        <p>The trip may have been deleted or the link is no longer valid.</p>
        <Link to="/" className="button button-primary">Back to trips</Link>
      </main>
    );
  }

  const selected = trip.route?.alternatives[trip.settings.selected_alternative] ?? trip.route?.alternatives[0] ?? null;
  const outsideExtract = trip.stops.some((stop) => !pointInExtract(stop.lon, stop.lat, health.data?.bounds ?? null));
  const coverage = coverageHint(health.data?.profile, health.data?.provider_mode);
  const routeBlockedReason =
    trip.stops.length < 2
      ? "Add at least two stops to build a route."
      : outsideExtract
        ? `Some stops are outside the current map coverage.${coverage ? ` ${coverage}` : ""}`
        : null;
  const optimizeBlockedReason =
    trip.stops.length < 3 ? "Add at least three stops to optimize their order." : routeBlockedReason;

  const panel =
    activePanel === "search" ? (
      <SearchBox
        onSelect={addOrReplacePlace}
        onPreview={setPreviewPlace}
        health={health.data}
        viewport={viewport}
        disabled={actions.busy}
        editingName={editingStop?.name}
      />
    ) : activePanel === "stops" ? (
      <StopList
        trip={trip}
        selectedStopId={selectedStopId}
        disabled={actions.busy}
        onChange={(stops) => void actions.replaceStops(stops).catch(() => undefined)}
        onSelect={(stopId) => updatePlannerSearch({ panel: "stops", stop: stopId })}
        onReplace={(stopId) => {
          setEditingStopId(stopId);
          updatePlannerSearch({ panel: "search", stop: stopId });
        }}
        onRemove={(stopId) => void removeStop(stopId)}
      />
    ) : activePanel === "options" ? (
      <RouteOptions
        trip={trip}
        disabled={actions.busy}
        pending={actions.settingsBusy}
        error={actions.settingsError?.message}
        onToggle={(key) => void actions.updateSettings({ [key]: !trip.settings[key] }).catch(() => undefined)}
      />
    ) : (
      <Directions
        trip={trip}
        disabled={actions.busy}
        pending={actions.settingsBusy}
        error={actions.settingsError?.message}
        onSelectAlternative={(index) => void actions.updateSettings({ selected_alternative: index }).catch(() => undefined)}
      />
    );

  return (
    <main id="main-content" className="planner-shell" tabIndex={-1}>
      <aside className="planner-panel" data-expanded={sheetExpanded} aria-label="Trip planner">
        <button
          ref={sheetToggleRef}
          type="button"
          className="sheet-toggle"
          aria-expanded={sheetExpanded}
          aria-controls="planner-sheet-content"
          onClick={() => setSheetExpanded((value) => !value)}
        >
          <span className="sheet-grabber" aria-hidden="true" />
          <span>{sheetExpanded ? "Collapse planner" : "Expand planner"}</span>
          {sheetExpanded ? <ChevronDown aria-hidden="true" size={18} /> : <ChevronUp aria-hidden="true" size={18} />}
        </button>

        <div id="planner-sheet-content" className="planner-panel-content">
          <header className="planner-header">
            <Link to="/" className="planner-back">← All trips</Link>
            <h1 className="sr-only">{trip.name}</h1>
            <div className="planner-title-row">
              <label className="sr-only" htmlFor="planner-trip-name">Trip name</label>
              <input
                id="planner-trip-name"
                className="planner-title-input"
                type="text"
                value={draftName}
                maxLength={120}
                disabled={actions.busy}
                onChange={(event) => setDraftName(event.target.value)}
                onBlur={() => void saveName()}
                onKeyDown={(event) => {
                  if (event.key === "Enter") event.currentTarget.blur();
                  if (event.key === "Escape") {
                    skipNextBlurRef.current = true;
                    setDraftName(trip.name);
                    event.currentTarget.blur();
                  }
                }}
              />
              <button
                type="button"
                className="icon-button planner-delete"
                aria-label={`Delete ${trip.name}`}
                disabled={actions.busy}
                onClick={() => {
                  actions.resetDelete();
                  setDeleteOpen(true);
                }}
              >
                <Trash2 aria-hidden="true" size={18} />
              </button>
            </div>
            <div className="title-save-state" aria-live="polite">
              {actions.nameBusy ? "Saving name…" : actions.nameError ? actions.nameError.message : ""}
            </div>
          </header>

          <PlannerTabs active={activePanel} onChange={setPanel} />

          <div className="planner-panel-body">
            <div
              id="planner-tabpanel"
              role="tabpanel"
              aria-labelledby={`planner-tab-${activePanel}`}
              tabIndex={0}
            >
              {editingStop && activePanel === "search" ? (
                <div className="edit-stop-banner">
                  <span>
                    Changing location for{" "}
                    <strong>
                      {editingStop.region ? `${editingStop.name} · ${editingStop.region}` : editingStop.name}
                    </strong>
                  </span>
                  <button type="button" onClick={() => setEditingStopId(null)}>Cancel</button>
                </div>
              ) : null}
              {panel}
            </div>
            {actions.stopError ? <StatusNotice variant="error">{actions.stopError.message}</StatusNotice> : null}
          </div>

          <footer className="planner-actions">
            <div className="route-actions">
              <button
                type="button"
                className="button button-primary"
                disabled={Boolean(routeBlockedReason) || actions.busy}
                aria-describedby={routeBlockedReason ? "route-build-reason" : undefined}
                onClick={async () => {
                  try {
                    await actions.buildRoute();
                    updatePlannerSearch({ panel: "directions" });
                    setFitRouteNonce((value) => value + 1);
                    setSheetExpanded(false);
                  } catch {
                    setSheetExpanded(true);
                  }
                }}
              >
                {actions.routeBusy ? <LoaderCircle className="spin" aria-hidden="true" size={18} /> : null}
                {actions.routeBusy ? "Building route…" : "Build route"}
              </button>
              {routeBlockedReason ? <span id="route-build-reason" className="sr-only">{routeBlockedReason}</span> : null}
              <button
                type="button"
                className="button button-secondary"
                disabled={Boolean(optimizeBlockedReason) || actions.busy}
                aria-describedby={optimizeBlockedReason ? "route-optimize-reason" : undefined}
                onClick={async () => {
                  try {
                    await actions.optimizeRoute();
                    updatePlannerSearch({ panel: "directions" });
                    setFitRouteNonce((value) => value + 1);
                    setSheetExpanded(false);
                  } catch {
                    setSheetExpanded(true);
                  }
                }}
              >
                <Sparkles aria-hidden="true" size={17} />
                {actions.optimizeBusy ? "Optimizing…" : "Optimize"}
              </button>
              {optimizeBlockedReason ? <span id="route-optimize-reason" className="sr-only">{optimizeBlockedReason}</span> : null}
            </div>
            <div id="route-action-hint" className="route-action-hint" aria-live="polite">
              <span>
                {selected ? (
                  <><strong>{formatDistance(selected.distance_m)}</strong> · {formatDuration(selected.duration_s)}</>
                ) : (
                  routeBlockedReason ?? "Build the route when your stops look right."
                )}
              </span>
              {optimizeBlockedReason && optimizeBlockedReason !== routeBlockedReason ? (
                <span>{optimizeBlockedReason}</span>
              ) : null}
            </div>
            {actions.routeError ? (
              <StatusNotice variant="error">
                {formatRoutingError(actions.routeError.message, health.data?.profile, health.data?.provider_mode)}
              </StatusNotice>
            ) : null}
            {actions.optimizeError ? (
              <StatusNotice variant="error">
                {formatRoutingError(actions.optimizeError.message, health.data?.profile, health.data?.provider_mode)}
              </StatusNotice>
            ) : null}
          </footer>
        </div>
      </aside>

      <MapView
        trip={trip}
        selectedStopId={selectedStopId}
        writeLocked={actions.busy}
        fitRouteNonce={fitRouteNonce}
        previewPlace={activePanel === "search" ? previewPlace : null}
        onViewportChange={setViewport}
        onSelectStop={(stopId) => updatePlannerSearch({ panel: "stops", stop: stopId })}
        onAddStop={(lon, lat) => void addMapStop(lon, lat)}
        onMoveStop={(stopId, lon, lat) => void moveMapStop(stopId, lon, lat)}
      />

      <div className="planner-notice-layer">
        {notice ? (
          <StatusNotice
            variant={notice.variant}
            actionLabel={notice.actionLabel}
            actionDisabled={actions.busy}
            onAction={notice.action ? () => void notice.action?.() : undefined}
          >
            {notice.message}
          </StatusNotice>
        ) : null}
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title="Delete this trip?"
        description={`“${trip.name}” and all of its stops and saved route data will be permanently deleted.`}
        confirmLabel="Delete trip"
        busy={actions.deleteBusy}
        error={actions.deleteError?.message}
        onCancel={() => {
          actions.resetDelete();
          setDeleteOpen(false);
        }}
        onConfirm={async () => {
          try {
            await actions.deleteTrip();
            await navigate({ to: "/" });
          } catch {
            // Keep the confirmation open so the error and retry remain available.
          }
        }}
      />
    </main>
  );
}
