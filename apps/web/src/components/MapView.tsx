import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { CircleHelp, LocateFixed, X } from "lucide-react";
import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { coverageHint, hasExplicitCamera, initialMapCamera } from "../lib/mapCamera";
import { commitMapPoint, coverageDropHint } from "../lib/mapInteraction";
import { syncTripRouteLayer, type RouteMap } from "../lib/mapRouteLayer";
import { mapLoadFailure, plannerMapStyle, usesLocalPmtiles } from "../lib/mapStyle";
import type { Trip, ViewportBounds } from "../lib/types";
import { tripRoute } from "../router";
import "maplibre-gl/dist/maplibre-gl.css";

let protocolRegistered = false;

function ensurePmtilesProtocol() {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

function fitCoordinates(map: maplibregl.Map, coordinates: number[][]) {
  if (!coordinates.length) return;
  if (coordinates.length === 1) {
    map.easeTo({ center: [coordinates[0][0], coordinates[0][1]], zoom: Math.max(map.getZoom(), 8), duration: 500 });
    return;
  }
  const bounds = coordinates.reduce(
    (next, coordinate) => next.extend([coordinate[0], coordinate[1]]),
    new maplibregl.LngLatBounds([coordinates[0][0], coordinates[0][1]], [coordinates[0][0], coordinates[0][1]]),
  );
  const compact = window.matchMedia("(max-width: 899px)").matches;
  map.fitBounds(bounds, {
    padding: compact ? { top: 56, right: 40, bottom: 190, left: 40 } : 64,
    maxZoom: 11,
    duration: 600,
  });
}

function collapseCompactAttribution(map: maplibregl.Map) {
  const attribution = map.getContainer().querySelector<HTMLElement>(".maplibregl-ctrl-attrib.maplibregl-compact");
  attribution?.classList.remove("maplibregl-compact-show");
  attribution?.removeAttribute("open");
}

type Props = {
  trip: Trip;
  selectedStopId: string | null;
  writeLocked: boolean;
  fitRouteNonce: number;
  onAddStop: (lon: number, lat: number) => void;
  onMoveStop: (stopId: string, lon: number, lat: number) => void;
  onSelectStop: (stopId: string) => void;
  onViewportChange: (viewport: ViewportBounds) => void;
};

export function MapView({
  trip,
  selectedStopId,
  writeLocked,
  fitRouteNonce,
  onAddStop,
  onMoveStop,
  onSelectStop,
  onViewportChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const appliedStyleRef = useRef<string | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const tripRef = useRef(trip);
  tripRef.current = trip;
  const selectedStopRef = useRef(selectedStopId);
  selectedStopRef.current = selectedStopId;
  const addStopRef = useRef(onAddStop);
  addStopRef.current = onAddStop;
  const moveStopRef = useRef(onMoveStop);
  moveStopRef.current = onMoveStop;
  const selectStopRef = useRef(onSelectStop);
  selectStopRef.current = onSelectStop;
  const viewportChangeRef = useRef(onViewportChange);
  viewportChangeRef.current = onViewportChange;
  const writeLockedRef = useRef(writeLocked);
  writeLockedRef.current = writeLocked;
  const draggingStopIdRef = useRef<string | null>(null);
  const fittedRouteNonceRef = useRef(0);
  const previousSelectedStopRef = useRef<string | null | undefined>(undefined);
  const suppressMapClickRef = useRef(false);
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const search = useSearch({ from: "/trips/$tripId" });
  const initialSearchRef = useRef(search);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const healthRef = useRef(health.data);
  healthRef.current = health.data;
  const mapsAvailable = health.data?.maps === true;
  const hosted = health.data?.provider_mode === "hosted";
  const selected = trip.route?.alternatives[trip.settings.selected_alternative] ?? trip.route?.alternatives[0];
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [clickHint, setClickHint] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const boundsRef = useRef(health.data?.bounds ?? null);
  boundsRef.current = health.data?.bounds ?? null;
  const profileRef = useRef(health.data?.profile ?? null);
  profileRef.current = health.data?.profile ?? null;
  const modeRef = useRef(health.data?.provider_mode);
  modeRef.current = health.data?.provider_mode;
  const healthReady = !health.isPending;

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !healthReady) return;
    const payload = healthRef.current;
    if (usesLocalPmtiles(payload)) ensurePmtilesProtocol();
    const camera = initialMapCamera(initialSearchRef.current, payload?.bounds ?? null);
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: plannerMapStyle(payload),
      ...(camera.kind === "center"
        ? { center: camera.center, zoom: camera.zoom }
        : { bounds: camera.bounds, fitBoundsOptions: { padding: 48, maxZoom: 11 } }),
      attributionControl: { compact: true },
    });
    appliedStyleRef.current = JSON.stringify({
      maps: payload?.maps ?? false,
      providerMode: payload?.provider_mode ?? null,
      styleUrl: payload?.map_style_url ?? null,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      collapseCompactAttribution(map);
      syncTripRouteLayer(map as unknown as RouteMap, selectedRef.current?.geometry);
      if (!hasExplicitCamera(initialSearchRef.current) && tripRef.current.stops.length) {
        fitCoordinates(map, tripRef.current.stops.map((stop) => [stop.lon, stop.lat]));
      }
    });
    map.on("error", (event) => {
      const error = event.error as { status?: number; message?: string } | undefined;
      const message = mapLoadFailure(error);
      if (message) setClickHint(message);
    });
    map.on("click", (event) => {
      if (draggingStopIdRef.current || suppressMapClickRef.current || writeLockedRef.current) return;
      const { lng, lat } = event.lngLat;
      const committed = commitMapPoint(lng, lat, boundsRef.current);
      if (!committed.ok) {
        const extra = coverageHint(profileRef.current, modeRef.current);
        setClickHint(extra ? `Click inside the map coverage. ${extra}` : "Click inside the map coverage.");
        return;
      }
      setClickHint(null);
      addStopRef.current(committed.lon, committed.lat);
    });
    map.on("moveend", () => {
      const center = map.getCenter();
      const bounds = map.getBounds();
      viewportChangeRef.current({
        west: bounds.getWest(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        north: bounds.getNorth(),
      });
      void navigateRef.current({
        from: tripRoute.fullPath,
        replace: true,
        search: (previous) => ({
          ...previous,
          lat: Number(center.lat.toFixed(5)),
          lng: Number(center.lng.toFixed(5)),
          z: Number(map.getZoom().toFixed(2)),
        }),
      });
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(map.getContainer());
    mapRef.current = map;
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, [healthReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !health.data) return;
    const styleKey = JSON.stringify({
      maps: health.data.maps,
      providerMode: health.data.provider_mode,
      styleUrl: health.data.map_style_url,
    });
    if (styleKey === appliedStyleRef.current) return;
    if (usesLocalPmtiles(health.data)) ensurePmtilesProtocol();
    appliedStyleRef.current = styleKey;
    map.setStyle(plannerMapStyle(health.data));
    map.once("style.load", () => {
      collapseCompactAttribution(map);
      syncTripRouteLayer(map as unknown as RouteMap, selectedRef.current?.geometry);
    });
  }, [health.data]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || draggingStopIdRef.current) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = trip.stops.map((stop, index) => {
      const element = document.createElement("button");
      element.type = "button";
      element.className = "trip-marker";
      element.dataset.selected = String(stop.id === selectedStopId);
      element.textContent = String(index + 1);
      element.setAttribute("aria-label", `${index + 1}. ${stop.name}. Select or drag to move.`);
      element.disabled = writeLocked;
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        selectStopRef.current(stop.id);
      });
      const marker = new maplibregl.Marker({ element, draggable: !writeLocked })
        .setLngLat([stop.lon, stop.lat])
        .setPopup(new maplibregl.Popup({ closeOnClick: true }).setText(`${index + 1}. ${stop.name}`))
        .addTo(map);
      marker.on("dragstart", () => {
        draggingStopIdRef.current = stop.id;
        marker.getPopup()?.remove();
        element.dataset.dragging = "true";
      });
      marker.on("dragend", () => {
        const { lng, lat } = marker.getLngLat();
        const committed = commitMapPoint(lng, lat, boundsRef.current);
        draggingStopIdRef.current = null;
        element.dataset.dragging = "false";
        suppressMapClickRef.current = true;
        window.setTimeout(() => {
          suppressMapClickRef.current = false;
        }, 300);
        if (!committed.ok) {
          marker.setLngLat([stop.lon, stop.lat]);
          setClickHint(coverageDropHint(profileRef.current, modeRef.current));
          return;
        }
        setClickHint(null);
        moveStopRef.current(stop.id, committed.lon, committed.lat);
      });
      return marker;
    });
  }, [selectedStopId, trip.stops, writeLocked]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    syncTripRouteLayer(map as unknown as RouteMap, selected?.geometry);
  }, [selected]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const initialSelection = previousSelectedStopRef.current === undefined;
    if (!initialSelection && previousSelectedStopRef.current === selectedStopId) return;
    previousSelectedStopRef.current = selectedStopId;
    if (!selectedStopId || (initialSelection && hasExplicitCamera(initialSearchRef.current))) return;
    const stop = trip.stops.find((item) => item.id === selectedStopId);
    if (stop) map.easeTo({ center: [stop.lon, stop.lat], zoom: Math.max(map.getZoom(), 7), duration: 450 });
  }, [selectedStopId, trip.stops]);

  useEffect(() => {
    const map = mapRef.current;
    if (
      !map ||
      fitRouteNonce === 0 ||
      fittedRouteNonceRef.current === fitRouteNonce ||
      !selected?.geometry.coordinates.length
    ) return;
    fittedRouteNonceRef.current = fitRouteNonce;
    fitCoordinates(map, selected.geometry.coordinates);
  }, [fitRouteNonce, selected]);

  const recenter = () => {
    const map = mapRef.current;
    if (!map) return;
    const coordinates = selected?.geometry.coordinates.length
      ? selected.geometry.coordinates
      : trip.stops.map((stop) => [stop.lon, stop.lat]);
    if (coordinates.length) fitCoordinates(map, coordinates);
  };

  return (
    <section className="map-wrap" aria-label="Trip map workspace">
      <div ref={containerRef} className="map-canvas" role="region" aria-label="Interactive trip map" />
      <div className="map-tools" aria-label="Map tools">
        <button type="button" className="map-tool-button" aria-label="Recenter on trip" onClick={recenter} disabled={!trip.stops.length}>
          <LocateFixed aria-hidden="true" size={19} />
          <span>Recenter</span>
        </button>
        <button type="button" className="map-tool-button" aria-label="Map help" aria-expanded={helpOpen} onClick={() => setHelpOpen((value) => !value)}>
          <CircleHelp aria-hidden="true" size={19} />
          <span>Map help</span>
        </button>
      </div>
      {helpOpen ? (
        <div className="map-help" role="status">
          <button type="button" className="icon-button" aria-label="Close map help" onClick={() => setHelpOpen(false)}>
            <X aria-hidden="true" size={18} />
          </button>
          <strong>Planning on the map</strong>
          <p>Click empty map to add a stop. Select a numbered pin to find it in the itinerary, or drag it to move.</p>
          <small>
            {hosted
              ? "Tiles: OpenFreeMap · Search: Photon · Routes: OpenRouteService"
              : "Local PMTiles, place index, and Valhalla routing. Nothing is sent to the cloud."}
          </small>
        </div>
      ) : null}
      {!mapsAvailable ? (
        <div className="map-banner" role="alert">{health.data?.detail ?? "The map source is unavailable."}</div>
      ) : clickHint ? (
        <div className="map-banner" role="status">{clickHint}</div>
      ) : null}
    </section>
  );
}
