import type {
  HealthResponse,
  RouteResponse,
  SearchResponse,
  Stop,
  Trip,
  TripSettings,
  TripSummary,
} from "./types";
import { coverageHint } from "./mapCamera";

export function formatApiErrorDetail(detail: unknown): string | undefined {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const message = (item as { msg: unknown }).msg;
          return typeof message === "string" ? message : undefined;
        }
        return undefined;
      })
      .filter((item): item is string => Boolean(item));
    return parts.length ? parts.join("; ") : undefined;
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return undefined;
}

export function formatRoutingError(
  message: string,
  profile?: string | null,
  providerMode?: HealthResponse["provider_mode"],
): string {
  if (message.includes("No suitable edges near location") || /"error_code"\s*:\s*171/.test(message)) {
    const extra = coverageHint(profile, providerMode);
    return extra
      ? `No roads near those stops in the local Valhalla graph. ${extra}`
      : "No roads near those stops in the local Valhalla graph.";
  }
  return message;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      detail = formatApiErrorDetail(payload.detail) ?? detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  search: (query: string, viewport?: { west: number; south: number; east: number; north: number }) => {
    const params = new URLSearchParams({ q: query });
    if (viewport) {
      params.set("west", String(viewport.west));
      params.set("south", String(viewport.south));
      params.set("east", String(viewport.east));
      params.set("north", String(viewport.north));
    }
    return request<SearchResponse>(`/api/search?${params.toString()}`);
  },
  listTrips: () => request<TripSummary[]>("/api/trips"),
  createTrip: (name: string) => request<Trip>("/api/trips", { method: "POST", body: JSON.stringify({ name }) }),
  getTrip: (id: string) => request<Trip>(`/api/trips/${id}`),
  updateTrip: (id: string, payload: { name?: string; settings?: Partial<TripSettings> }) =>
    request<Trip>(`/api/trips/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteTrip: (id: string) => request<void>(`/api/trips/${id}`, { method: "DELETE" }),
  replaceStops: (id: string, stops: Array<Pick<Stop, "name" | "lon" | "lat" | "place_id"> & { id?: string }>) =>
    request<Trip>(`/api/trips/${id}/stops`, { method: "PUT", body: JSON.stringify(stops) }),
  routeTrip: (id: string) => request<RouteResponse>(`/api/trips/${id}/route`, { method: "POST" }),
  optimizeTrip: (id: string) => request<RouteResponse>(`/api/trips/${id}/optimize`, { method: "POST" }),
};
