import type { ViewportBounds } from "./types";

export function haversineMeters(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const radius = 6_371_000;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(a));
}

export function viewportCenter(viewport: ViewportBounds | null | undefined): { lon: number; lat: number } | null {
  if (!viewport) return null;
  const lon =
    viewport.west <= viewport.east
      ? (viewport.west + viewport.east) / 2
      : ((viewport.west + viewport.east + 360) / 2 + 180) % 360 - 180;
  return {
    lon,
    lat: (viewport.south + viewport.north) / 2,
  };
}
