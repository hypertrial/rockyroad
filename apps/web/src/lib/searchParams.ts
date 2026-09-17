import type { PlannerSearch } from "./types";

export function validatePlannerSearch(raw: Record<string, unknown>): PlannerSearch {
  const lat = toNumber(raw.lat, -90, 90);
  const lng = toNumber(raw.lng, -180, 180);
  const z = toNumber(raw.z, 0, 22);
  const stop = typeof raw.stop === "string" ? raw.stop : undefined;
  const panel = isPanel(raw.panel) ? raw.panel : undefined;
  return {
    ...(lat !== undefined ? { lat } : {}),
    ...(lng !== undefined ? { lng } : {}),
    ...(z !== undefined ? { z } : {}),
    ...(stop ? { stop } : {}),
    ...(panel ? { panel } : {}),
  };
}

function toNumber(value: unknown, minimum: number, maximum: number): number | undefined {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum ? parsed : undefined;
}

function isPanel(value: unknown): value is PlannerSearch["panel"] {
  return value === "search" || value === "stops" || value === "directions" || value === "options";
}
