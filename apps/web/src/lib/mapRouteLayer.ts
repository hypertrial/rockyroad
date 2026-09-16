export const TRIP_ROUTE_SOURCE_ID = "trip-route";
export const TRIP_ROUTE_LAYER_ID = "trip-route-line";

export const EMPTY_ROUTE_GEOMETRY = {
  type: "LineString" as const,
  coordinates: [] as number[][],
};

export type RouteGeometry = {
  type: "LineString";
  coordinates: number[][];
};

export type RouteFeature = {
  type: "Feature";
  properties: Record<string, never>;
  geometry: RouteGeometry;
};

export type RouteMap = {
  isStyleLoaded: () => boolean | void;
  getSource: (id: string) => { setData: (data: RouteFeature) => void } | undefined;
  addSource: (id: string, source: { type: "geojson"; data: RouteFeature }) => void;
  addLayer: (layer: {
    id: string;
    type: "line";
    source: string;
    paint: Record<string, unknown>;
  }) => void;
};

export function routeFeature(geometry: RouteGeometry | null | undefined): RouteFeature {
  return {
    type: "Feature",
    properties: {},
    geometry: geometry ?? EMPTY_ROUTE_GEOMETRY,
  };
}

export function syncTripRouteLayer(map: RouteMap, geometry: RouteGeometry | null | undefined): boolean {
  if (!map.isStyleLoaded()) return false;
  const data = routeFeature(geometry);
  const existing = map.getSource(TRIP_ROUTE_SOURCE_ID);
  if (existing) {
    existing.setData(data);
    return true;
  }
  map.addSource(TRIP_ROUTE_SOURCE_ID, { type: "geojson", data });
  map.addLayer({
    id: TRIP_ROUTE_LAYER_ID,
    type: "line",
    source: TRIP_ROUTE_SOURCE_ID,
    paint: {
      "line-color": "#b4532a",
      "line-width": 4,
      "line-opacity": 0.9,
    },
  });
  return true;
}
