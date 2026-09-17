import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { coverageHint, initialMapCamera } from "../lib/mapCamera";
import { commitMapPoint, coverageDropHint } from "../lib/mapInteraction";
import { syncTripRouteLayer, type RouteMap } from "../lib/mapRouteLayer";
import { plannerMapStyle, usesLocalPmtiles } from "../lib/mapStyle";
import type { Trip } from "../lib/types";
import { tripRoute } from "../router";
import { useUiStore } from "../stores/ui";
import "maplibre-gl/dist/maplibre-gl.css";

let protocolRegistered = false;

function ensurePmtilesProtocol() {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

type Props = {
  trip: Trip;
  onAddStop: (lon: number, lat: number) => void;
  onMoveStop: (stopId: string, lon: number, lat: number) => void;
};

export function MapView({ trip, onAddStop, onMoveStop }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const addStopRef = useRef(onAddStop);
  addStopRef.current = onAddStop;
  const moveStopRef = useRef(onMoveStop);
  moveStopRef.current = onMoveStop;
  const draggingStopIdRef = useRef<string | null>(null);
  const suppressMapClickRef = useRef(false);
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const search = useSearch({ from: "/trips/$tripId" });
  const initialSearchRef = useRef(search);
  const selectedStopId = useUiStore((state) => state.selectedStopId);
  const setMapReady = useUiStore((state) => state.setMapReady);
  const setViewport = useUiStore((state) => state.setViewport);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const healthRef = useRef(health.data);
  healthRef.current = health.data;
  const mapsAvailable = health.data?.maps === true;
  const hosted = health.data?.provider_mode === "hosted";
  const selected = trip.route?.alternatives[trip.settings.selected_alternative] ?? trip.route?.alternatives[0];
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [clickHint, setClickHint] = useState<string | null>(null);
  const bounds = health.data?.bounds ?? null;
  const boundsKey = bounds?.join(",") ?? "";
  const mapStyleUrl = health.data?.map_style_url ?? "";
  const providerMode = health.data?.provider_mode ?? "";
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const profileRef = useRef(health.data?.profile ?? null);
  profileRef.current = health.data?.profile ?? null;
  const modeRef = useRef(health.data?.provider_mode);
  modeRef.current = health.data?.provider_mode;

  useEffect(() => {
    if (!containerRef.current || mapRef.current || health.isPending) return;
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
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      setMapReady(true);
      syncTripRouteLayer(map as unknown as RouteMap, selectedRef.current?.geometry);
    });
    map.on("error", (event) => {
      const error = event.error as { status?: number; message?: string } | undefined;
      if (error?.status === 404 || error?.message?.includes("404")) {
        setMapReady(false);
      }
    });
    map.on("click", (event) => {
      if (draggingStopIdRef.current || suppressMapClickRef.current) return;
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
      setViewport({
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
    const resize = () => map.resize();
    const observer = new ResizeObserver(resize);
    observer.observe(map.getContainer());
    mapRef.current = map;
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [boundsKey, health.isPending, mapStyleUrl, mapsAvailable, providerMode, setMapReady, setViewport]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || draggingStopIdRef.current) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = trip.stops.map((stop, index) => {
      const marker = new maplibregl.Marker({
        color: stop.id === selectedStopId ? "#b4532a" : "#2d4a3e",
        draggable: true,
      })
        .setLngLat([stop.lon, stop.lat])
        .setPopup(new maplibregl.Popup({ closeOnClick: true }).setText(`${index + 1}. ${stop.name}`))
        .addTo(map);
      marker.getElement().setAttribute("aria-label", `Drag to move ${stop.name}`);
      marker.on("dragstart", () => {
        draggingStopIdRef.current = stop.id;
        marker.getPopup()?.remove();
      });
      marker.on("dragend", () => {
        const { lng, lat } = marker.getLngLat();
        const committed = commitMapPoint(lng, lat, boundsRef.current);
        draggingStopIdRef.current = null;
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
  }, [selectedStopId, trip.stops]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    syncTripRouteLayer(map as unknown as RouteMap, selected?.geometry);
  }, [selected]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" role="application" aria-label="Trip map" />
      {!mapsAvailable ? (
        <div className="map-banner">{health.data?.detail ?? "The map source is unavailable."}</div>
      ) : clickHint ? (
        <div className="map-banner">{clickHint}</div>
      ) : null}
      <div className="map-legend">
        {hosted
          ? "Drag the map to pan. Drag a pin to move a stop. Click empty map to add a stop. Tiles come from OpenFreeMap; search and routes go through RockyRoad."
          : "Drag the map to pan. Drag a pin to move a stop. Click inside the downloaded map to add a stop. Nothing is sent to the cloud."}
      </div>
    </div>
  );
}
