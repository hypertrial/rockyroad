import type { HealthResponse, PlannerSearch } from "./types";

export const CONTINENT_CENTER: [number, number] = [-96.5, 48.5];
export const CONTINENT_ZOOM = 3.4;

export type MapCamera =
  | { kind: "center"; center: [number, number]; zoom: number }
  | { kind: "bounds"; bounds: [[number, number], [number, number]] };

function isSampleSized(bounds: number[]): boolean {
  const [west, south, east, north] = bounds;
  return east - west < 10 && north - south < 10;
}

export function initialMapCamera(search: PlannerSearch, bounds: HealthResponse["bounds"]): MapCamera {
  const urlReady = search.lat !== undefined && search.lng !== undefined && search.z !== undefined;
  if (bounds && bounds.length === 4 && (!urlReady || ((search.z ?? 0) < 5 && isSampleSized(bounds)))) {
    const [west, south, east, north] = bounds;
    return {
      kind: "bounds",
      bounds: [
        [west, south],
        [east, north],
      ],
    };
  }
  if (urlReady) {
    return { kind: "center", center: [search.lng as number, search.lat as number], zoom: search.z as number };
  }
  return { kind: "center", center: CONTINENT_CENTER, zoom: CONTINENT_ZOOM };
}
