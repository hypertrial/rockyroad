import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { coverageHint, initialMapCamera, pointInExtract } from "../lib/mapCamera";
import { syncTripRouteLayer, type RouteMap } from "../lib/mapRouteLayer";
import { plannerMapStyle } from "../lib/mapStyle";
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
};

export function MapView({ trip, onAddStop }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const addStopRef = useRef(onAddStop);
  addStopRef.current = onAddStop;
  const navigate = useNavigate();
  const search = useSearch({ from: "/trips/$tripId" });
  const initialSearchRef = useRef(search);
  const selectedStopId = useUiStore((state) => state.selectedStopId);
  const setMapReady = useUiStore((state) => state.setMapReady);
  const setViewport = useUiStore((state) => state.setViewport);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const mapsAvailable = health.data?.maps === true;
  const selected = trip.route?.alternatives[trip.settings.selected_alternative] ?? trip.route?.alternatives[0];
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [clickHint, setClickHint] = useState<string | null>(null);
  const bounds = health.data?.bounds ?? null;
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const profileRef = useRef(health.data?.profile ?? null);
  profileRef.current = health.data?.profile ?? null;

  useEffect(() => {
    if (!containerRef.current || mapRef.current || health.isPending) return;
    if (mapsAvailable) ensurePmtilesProtocol();
    const camera = initialMapCamera(initialSearchRef.current, health.data?.bounds ?? null);
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: plannerMapStyle(mapsAvailable),
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
      const { lng, lat } = event.lngLat;
      if (!pointInExtract(lng, lat, boundsRef.current)) {
        const extra = coverageHint(profileRef.current);
        setClickHint(extra ? `Click inside the downloaded map. ${extra}` : "Click inside the downloaded map.");
        return;
      }
      setClickHint(null);
      addStopRef.current(lng, lat);
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
      void navigate({
        from: tripRoute.fullPath,
        search: (previous) => ({
          ...previous,
          lat: Number(center.lat.toFixed(5)),
          lng: Number(center.lng.toFixed(5)),
          z: Number(map.getZoom().toFixed(2)),
        }),
      });
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [health.data?.bounds, health.isPending, mapsAvailable, navigate, setMapReady, setViewport]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = trip.stops.map((stop, index) => {
      const marker = new maplibregl.Marker({ color: stop.id === selectedStopId ? "#b4532a" : "#2d4a3e" })
        .setLngLat([stop.lon, stop.lat])
        .setPopup(new maplibregl.Popup().setText(`${index + 1}. ${stop.name}`))
        .addTo(map);
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
        <div className="map-banner">{health.data?.detail ?? "Local PMTiles are missing."}</div>
      ) : clickHint ? (
        <div className="map-banner">{clickHint}</div>
      ) : null}
      <div className="map-legend">Click inside the downloaded map to drop a stop. Nothing is sent to the cloud.</div>
    </div>
  );
}
