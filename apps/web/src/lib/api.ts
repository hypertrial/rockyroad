import type {
  HealthResponse,
  PlaceResult,
  RouteResponse,
  SavedPlace,
  SearchResponse,
  Stop,
  Trip,
  TripSettings,
  TripSummary,
} from "./types";

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
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
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
  listSavedPlaces: () => request<SavedPlace[]>("/api/saved-places"),
  savePlace: (place: Pick<PlaceResult, "name" | "lon" | "lat" | "id">) =>
    request<SavedPlace>("/api/saved-places", {
      method: "POST",
      body: JSON.stringify({
        name: place.name,
        lon: place.lon,
        lat: place.lat,
        place_id: place.id,
      }),
    }),
};
