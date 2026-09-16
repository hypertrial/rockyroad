import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef } from "react";
import { api } from "../lib/api";
import { initialMapCamera } from "../lib/mapCamera";
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
    map.on("load", () => setMapReady(true));
    map.on("error", (event) => {
      const error = event.error as { status?: number; message?: string } | undefined;
      if (error?.status === 404 || error?.message?.includes("404")) {
        setMapReady(false);
      }
    });
    map.on("click", (event) => addStopRef.current(event.lngLat.lng, event.lngLat.lat));
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
    if (!map || !map.isStyleLoaded()) return;
    const sourceId = "trip-route";
    if (map.getSource(sourceId)) {
      const source = map.getSource(sourceId) as maplibregl.GeoJSONSource;
      source.setData({
        type: "Feature",
        properties: {},
        geometry: selected?.geometry ?? { type: "LineString", coordinates: [] },
      });
      return;
    }
    map.addSource(sourceId, {
      type: "geojson",
      data: {
        type: "Feature",
        properties: {},
        geometry: selected?.geometry ?? { type: "LineString", coordinates: [] },
      },
    });
    map.addLayer({
      id: "trip-route-line",
      type: "line",
      source: sourceId,
      paint: {
        "line-color": "#b4532a",
        "line-width": 4,
        "line-opacity": 0.9,
      },
    });
  }, [selected]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" role="application" aria-label="Trip map" />
      {!mapsAvailable ? (
        <div className="map-banner">{health.data?.detail ?? "Local PMTiles are missing."}</div>
      ) : null}
      <div className="map-legend">Click the map to drop a stop. Nothing is sent to the cloud.</div>
    </div>
  );
}
