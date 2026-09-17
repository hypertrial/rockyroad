import { coverageHint, pointInExtract } from "./mapCamera";
import type { HealthResponse, Stop } from "./types";

export type StopDraft = Pick<Stop, "name" | "lon" | "lat" | "place_id"> & { id?: string };

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

export function withMovedStop<T extends { id?: string; lon: number; lat: number; place_id: string | null }>(
  stops: T[],
  stopId: string,
  lon: number,
  lat: number,
): T[] {
  return stops.map((stop) => (stop.id === stopId ? { ...stop, lon, lat, place_id: null } : stop));
}

export function toStopDrafts(stops: Array<Pick<Stop, "id" | "name" | "lon" | "lat" | "place_id">>): StopDraft[] {
  return stops.map((stop) => ({
    id: stop.id,
    name: stop.name,
    lon: stop.lon,
    lat: stop.lat,
    place_id: stop.place_id,
  }));
}
