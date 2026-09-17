import type { HealthResponse, PlannerSearch } from "./types";

export const CONTINENT_CENTER: [number, number] = [-96.5, 48.5];
export const CONTINENT_ZOOM = 3.4;

export type MapCamera =
  | { kind: "center"; center: [number, number]; zoom: number }
  | { kind: "bounds"; bounds: [[number, number], [number, number]] };

export function hasExplicitCamera(search: PlannerSearch): boolean {
  return (
    search.lat !== undefined &&
    search.lat >= -90 &&
    search.lat <= 90 &&
    search.lng !== undefined &&
    search.lng >= -180 &&
    search.lng <= 180 &&
    search.z !== undefined &&
    search.z >= 0 &&
    search.z <= 22
  );
}

function isSampleSized(bounds: number[]): boolean {
  const [west, south, east, north] = bounds;
  return east - west < 10 && north - south < 10;
}

export function pointInExtract(lon: number, lat: number, bounds: HealthResponse["bounds"]): boolean {
  if (!bounds || bounds.length !== 4) return true;
  const [west, south, east, north] = bounds;
  return lon >= west && lon <= east && lat >= south && lat <= north;
}

export function coverageHint(
  profile: HealthResponse["profile"] | undefined,
  providerMode?: HealthResponse["provider_mode"],
): string {
  if (providerMode === "hosted") return "Stay inside Canada and the USA.";
  if (profile === "sample") return "With the sample extract, stay on Prince Edward Island.";
  if (profile) return `Stay inside the ${profile} extract.`;
  return "";
}

export function initialMapCamera(search: PlannerSearch, bounds: HealthResponse["bounds"]): MapCamera {
  if (hasExplicitCamera(search)) {
    return { kind: "center", center: [search.lng as number, search.lat as number], zoom: search.z as number };
  }
  if (bounds && bounds.length === 4 && isSampleSized(bounds)) {
    const [west, south, east, north] = bounds;
    return {
      kind: "bounds",
      bounds: [
        [west, south],
        [east, north],
      ],
    };
  }
  return { kind: "center", center: CONTINENT_CENTER, zoom: CONTINENT_ZOOM };
}
