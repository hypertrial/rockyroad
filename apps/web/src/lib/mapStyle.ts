import type { HealthResponse } from "./types";

export const EMPTY_MAP_STYLE = {
  version: 8 as const,
  name: "RockyRoad Empty",
  sources: {},
  layers: [
    {
      id: "background",
      type: "background" as const,
      paint: { "background-color": "#efe7d6" },
    },
  ],
};

export const LOCAL_TILE_STYLE = "/map/style.json";
export const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

export function plannerMapStyle(health?: Pick<HealthResponse, "maps" | "provider_mode" | "map_style_url"> | null) {
  if (!health) return EMPTY_MAP_STYLE;
  if (health.provider_mode === "hosted") {
    return health.maps && health.map_style_url ? health.map_style_url : EMPTY_MAP_STYLE;
  }
  return health.maps ? LOCAL_TILE_STYLE : EMPTY_MAP_STYLE;
}

export function usesLocalPmtiles(health?: Pick<HealthResponse, "maps" | "provider_mode"> | null) {
  return health?.provider_mode === "local" && health.maps === true;
}

export function mapLoadFailure(error: { status?: number; message?: string } | undefined): string | null {
  if (!error || /sprite|glyph|image/i.test(error.message ?? "")) return null;
  if (
    (error.status !== undefined && error.status >= 400) ||
    /\b4\d\d\b|\b5\d\d\b|failed to fetch|networkerror|load failed/i.test(error.message ?? "")
  ) {
    return "The map source is temporarily unavailable. Your trip data is still safe.";
  }
  return null;
}
