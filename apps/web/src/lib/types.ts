export type PlaceResult = {
  id: string;
  name: string;
  feature_type: string;
  dataset: string;
  lon: number;
  lat: number;
  score: number;
  population: number | null;
};

export type SearchResponse = {
  query: string;
  results: PlaceResult[];
};

export type Stop = {
  id: string;
  trip_id: string;
  position: number;
  name: string;
  lon: number;
  lat: number;
  place_id: string | null;
  created_at: string;
};

export type TripSettings = {
  trip_id: string;
  avoid_tolls: boolean;
  avoid_highways: boolean;
  avoid_ferries: boolean;
  costing: "auto";
  optimize: boolean;
  selected_alternative: number;
  updated_at: string;
};

export type Maneuver = {
  instruction: string;
  type: number | null;
  distance_m: number;
  duration_s: number;
  begin_shape_index: number;
};

export type RouteAlternative = {
  index: number;
  distance_m: number;
  duration_s: number;
  geometry: {
    type: "LineString";
    coordinates: number[][];
  };
  maneuvers: Maneuver[];
};

export type RouteResponse = {
  trip_id: string;
  cache_hit: boolean;
  data_version: string;
  alternatives: RouteAlternative[];
};

export type Trip = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  stops: Stop[];
  settings: TripSettings;
  route: RouteResponse | null;
};

export type TripSummary = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  stop_count: number;
};

export type SavedPlace = {
  id: string;
  name: string;
  lon: number;
  lat: number;
  place_id: string | null;
  notes: string | null;
  created_at: string;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  duckdb: boolean;
  geo: boolean;
  routing: boolean;
  maps: boolean;
  data_version: string | null;
  detail: string | null;
  bounds: number[] | null;
};

export type PlannerSearch = {
  lat?: number;
  lng?: number;
  z?: number;
  stop?: string;
  panel?: "search" | "stops" | "directions" | "options";
};
