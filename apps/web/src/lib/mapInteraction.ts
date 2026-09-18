import { coverageHint, pointInExtract } from "./mapCamera";
import type { HealthResponse, Stop } from "./types";

export type StopDraft = Pick<Stop, "name" | "lon" | "lat" | "place_id" | "region"> & { id?: string };

export function commitMapPoint(
  lon: number,
  lat: number,
  bounds: HealthResponse["bounds"],
): { ok: true; lon: number; lat: number } | { ok: false } {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return { ok: false };
  if (!pointInExtract(lon, lat, bounds)) return { ok: false };
  return { ok: true, lon, lat };
}

export function coverageDropHint(
  profile: HealthResponse["profile"] | undefined,
  providerMode?: HealthResponse["provider_mode"],
): string {
  const extra = coverageHint(profile, providerMode);
  return extra ? `Drop the pin inside the map coverage. ${extra}` : "Drop the pin inside the map coverage.";
}

export function withMovedStop<
  T extends { id?: string; lon: number; lat: number; place_id: string | null; region?: string | null },
>(stops: T[], stopId: string, lon: number, lat: number): T[] {
  return stops.map((stop) => (stop.id === stopId ? { ...stop, lon, lat, place_id: null, region: null } : stop));
}

export function toStopDrafts(
  stops: Array<Pick<Stop, "id" | "name" | "lon" | "lat" | "place_id" | "region">>,
): StopDraft[] {
  return stops.map((stop) => ({
    id: stop.id,
    name: stop.name,
    lon: stop.lon,
    lat: stop.lat,
    place_id: stop.place_id,
    region: stop.region ?? null,
  }));
}

export function restoreRemovedStop(
  currentStops: StopDraft[],
  removedStop: StopDraft,
  originalIndex: number,
): StopDraft[] {
  if (removedStop.id && currentStops.some((stop) => stop.id === removedStop.id)) return currentStops;
  const restored = [...currentStops];
  restored.splice(Math.min(Math.max(originalIndex, 0), restored.length), 0, removedStop);
  return restored;
}

export function attachOutsideReleaseForwarder(container: HTMLElement, doc: Document = document): () => void {
  let pressInMap = false;
  const onDown = () => {
    pressInMap = true;
  };
  const onUp = (event: MouseEvent) => {
    if (!pressInMap) return;
    pressInMap = false;
    if (event.target instanceof Node && container.contains(event.target)) return;
    container.dispatchEvent(
      new MouseEvent("mouseup", {
        bubbles: true,
        cancelable: true,
        button: event.button,
        buttons: 0,
        clientX: event.clientX,
        clientY: event.clientY,
      }),
    );
  };
  container.addEventListener("mousedown", onDown);
  doc.addEventListener("mouseup", onUp);
  return () => {
    container.removeEventListener("mousedown", onDown);
    doc.removeEventListener("mouseup", onUp);
  };
}
