import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { tripRoute } from "../router";
import type { Trip } from "../lib/types";
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
  const selectedStopId = useUiStore((state) => state.selectedStopId);
  const setMapReady = useUiStore((state) => state.setMapReady);
  const setViewport = useUiStore((state) => state.setViewport);
  const mapReady = useUiStore((state) => state.mapReady);
  const selected = trip.route?.alternatives[trip.settings.selected_alternative] ?? trip.route?.alternatives[0];

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    ensurePmtilesProtocol();
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "/map/style.json",
      center: [-96.5, 48.5],
      zoom: 3.4,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => setMapReady(true));
    map.on("error", () => setMapReady(false));
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
    };
  }, [navigate, setMapReady, setViewport]);

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
      {!mapReady ? (
        <div className="map-banner">
          Local tiles load from <code>/maps/north-america.pmtiles</code>. If the map is blank, run{" "}
          <code>uv run rockyroad-data build-map</code>.
        </div>
      ) : null}
      <div className="map-legend">Click the map to drop a stop. Drag nothing to the cloud.</div>
    </div>
  );
}
