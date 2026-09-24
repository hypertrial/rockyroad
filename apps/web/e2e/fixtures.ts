import type { Page, Route } from "@playwright/test";
import type { RouteResponse, Stop, Trip } from "../src/lib/types";

type MockOptions = {
  degraded?: boolean;
  empty?: boolean;
  manyStops?: boolean;
  routeReady?: boolean;
  longDirections?: boolean;
  outsideCoverage?: boolean;
  providerMode?: "hosted" | "local";
  tripListDelayMs?: number;
  healthDelayMs?: number;
  tripListFailureCount?: number;
  tripName?: string;
  routeSettingsFailure?: boolean;
  deleteFailureCount?: number;
  routeFailureCount?: number;
  mapStyleStatus?: number;
};

const now = "2026-09-17T08:00:00Z";

const routeResponse: RouteResponse = {
  trip_id: "trip-1",
  cache_hit: false,
  data_version: "test-v1",
  alternatives: [
    {
      index: 0,
      distance_m: 63500,
      duration_s: 4200,
      geometry: {
        type: "LineString",
        coordinates: [
          [-63.13, 46.24],
          [-63.79, 46.39],
        ],
      },
      maneuvers: [
        { instruction: "Head west on Water Street", type: 1, distance_m: 1200, duration_s: 110, begin_shape_index: 0 },
        { instruction: "Continue toward Summerside", type: 8, distance_m: 62300, duration_s: 4090, begin_shape_index: 1 },
      ],
    },
    {
      index: 1,
      distance_m: 68100,
      duration_s: 4480,
      geometry: {
        type: "LineString",
        coordinates: [
          [-63.13, 46.24],
          [-63.42, 46.51],
          [-63.79, 46.39],
        ],
      },
      maneuvers: [
        { instruction: "Take the scenic coastal road", type: 1, distance_m: 68100, duration_s: 4480, begin_shape_index: 0 },
      ],
    },
  ],
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function mockRockyRoad(page: Page, options: MockOptions = {}) {
  const baseStops: Stop[] = options.empty
    ? []
    : [
        { id: "stop-a", trip_id: "trip-1", position: 0, name: "Charlottetown", lon: -63.13, lat: 46.24, place_id: "p-a", created_at: now, region: "Prince Edward Island, Canada" },
        { id: "stop-b", trip_id: "trip-1", position: 1, name: "Summerside", lon: options.outsideCoverage ? -80 : -63.79, lat: 46.39, place_id: "p-b", created_at: now, region: null },
      ];
  const manyStops: Stop[] = options.manyStops
    ? Array.from({ length: 10 }, (_, index) => ({
        id: `stop-extra-${index}`,
        trip_id: "trip-1",
        position: index + baseStops.length,
        name: `Scenic stop ${index + 1} with a deliberately descriptive name`,
        lon: -63.1 - index * 0.05,
        lat: 46.2 + index * 0.025,
        place_id: `p-extra-${index}`,
        created_at: now,
        region: null,
      }))
    : [];
  const preparedRoute = options.longDirections
    ? {
        ...routeResponse,
        alternatives: routeResponse.alternatives.map((alternative) => ({
          ...alternative,
          maneuvers: Array.from({ length: 16 }, (_, index) => ({
            instruction: `${index + 1}. Continue along the coastal road toward the next signed viewpoint and rest area`,
            type: 8,
            distance_m: 800 + index * 275,
            duration_s: 90 + index * 20,
            begin_shape_index: index,
          })),
        })),
      }
    : routeResponse;
  let trip: Trip = {
    id: "trip-1",
    name: options.tripName ?? "Island slow road",
    created_at: now,
    updated_at: now,
    stops: [...baseStops, ...manyStops],
    settings: {
      trip_id: "trip-1",
      avoid_tolls: false,
      avoid_highways: false,
      avoid_ferries: false,
      optimize: false,
      costing: "auto",
      selected_alternative: 0,
      updated_at: now,
    },
    route: options.routeReady ? preparedRoute : null,
  };
  let deleted = false;
  let hasDashboardTrip = !options.empty;
  let tripListRequests = 0;
  let deleteRequests = 0;
  let routeRequests = 0;
  let stopReplacementRequests = 0;

  const fulfillMapStyle = (route: Route) =>
    json(route, {
      version: 8,
      name: "RockyRoad deterministic test style",
      sources: {
        localAttribution: {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
          attribution: "RockyRoad test map",
        },
      },
      layers: [
        { id: "background", type: "background", paint: { "background-color": "#dfe9e7" } },
        { id: "local-attribution", type: "circle", source: "localAttribution" },
      ],
    }, options.mapStyleStatus ?? 200);
  await page.route("**/mock-map-style.json", fulfillMapStyle);
  await page.route("**/map/style.json", fulfillMapStyle);

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (pathname === "/api/health") {
      if (options.healthDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.healthDelayMs));
      }
      return json(route, {
        status: options.degraded ? "degraded" : "ok",
        duckdb: true,
        geo: true,
        routing: !options.degraded,
        maps: true,
        data_version: "test-v1",
        detail: options.degraded ? "Routing is unavailable. Search and saved trips still work." : null,
        bounds: [-64.45, 45.9, -61.9, 47.1],
        profile: "sample",
        provider_mode: options.providerMode ?? "hosted",
        map_style_url: "/mock-map-style.json",
        map_provider: "test",
        routing_provider: "test",
        search_provider: "test",
      });
    }

    if (pathname === "/api/trips" && method === "GET") {
      tripListRequests += 1;
      if (options.tripListDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.tripListDelayMs));
      }
      if (tripListRequests <= (options.tripListFailureCount ?? 0)) {
        return json(route, { detail: "Saved trips are temporarily unavailable." }, 503);
      }
      return json(
        route,
        deleted || !hasDashboardTrip
          ? []
          : [{ id: trip.id, name: trip.name, created_at: trip.created_at, updated_at: trip.updated_at, stop_count: trip.stops.length }],
      );
    }

    if (pathname === "/api/trips" && method === "POST") {
      const body = request.postDataJSON() as { name: string };
      trip = { ...trip, name: body.name };
      hasDashboardTrip = true;
      return json(route, trip, 201);
    }

    if (pathname === "/api/trips/trip-1" && method === "GET") {
      return deleted ? json(route, { detail: "Not found" }, 404) : json(route, trip);
    }

    if (pathname === "/api/trips/trip-1" && method === "DELETE") {
      deleteRequests += 1;
      if (deleteRequests <= (options.deleteFailureCount ?? 0)) {
        return json(route, { detail: "Trip could not be deleted." }, 503);
      }
      deleted = true;
      hasDashboardTrip = false;
      return route.fulfill({ status: 204 });
    }

    if (pathname === "/api/trips/trip-1" && method === "PATCH") {
      const body = request.postDataJSON() as { name?: string; settings?: Partial<typeof trip.settings> };
      if (body.settings && options.routeSettingsFailure) {
        return json(route, { detail: "Route settings could not be saved." }, 503);
      }
      trip = {
        ...trip,
        ...(body.name ? { name: body.name } : {}),
        ...(body.settings ? { settings: { ...trip.settings, ...body.settings, updated_at: now } } : {}),
        route: body.settings && body.settings.selected_alternative === undefined ? null : trip.route,
      };
      return json(route, trip);
    }

    if (pathname === "/api/trips/trip-1/stops" && method === "PUT") {
      stopReplacementRequests += 1;
      const drafts = request.postDataJSON() as Array<{
        id?: string;
        name: string;
        lon: number;
        lat: number;
        place_id: string | null;
        region?: string | null;
      }>;
      trip = {
        ...trip,
        stops: drafts.map((stop, index) => ({
          ...stop,
          id: stop.id ?? `stop-${index + 1}`,
          trip_id: trip.id,
          position: index,
          created_at: now,
          region: stop.region ?? null,
        })),
        route: null,
      };
      return json(route, trip);
    }

    if (pathname === "/api/trips/trip-1/route" && method === "POST") {
      routeRequests += 1;
      if (routeRequests <= (options.routeFailureCount ?? 0)) {
        return json(route, { detail: "Routing provider unavailable." }, 503);
      }
      trip = { ...trip, route: routeResponse };
      return json(route, routeResponse);
    }

    if (pathname === "/api/trips/trip-1/optimize" && method === "POST") {
      trip = { ...trip, route: routeResponse, settings: { ...trip.settings, optimize: true } };
      return json(route, routeResponse);
    }

    if (pathname === "/api/search" && method === "GET") {
      const query = url.searchParams.get("q") ?? "";
      const results = query.toLowerCase().includes("vancouver")
        ? [
            {
              id: "p-van-bc",
              name: "Vancouver",
              feature_type: "city",
              dataset: "mock",
              lon: -123.11,
              lat: 49.26,
              score: 1,
              population: null,
              state: "British Columbia",
              country: "Canada",
              country_code: "CA",
              place_type: "city",
              region: "British Columbia, Canada",
            },
            {
              id: "p-van-wa",
              name: "Vancouver",
              feature_type: "city",
              dataset: "mock",
              lon: -122.67,
              lat: 45.63,
              score: 0.98,
              population: null,
              state: "Washington",
              country: "United States",
              country_code: "US",
              place_type: "city",
              region: "Washington, United States",
            },
          ]
        : [
            {
              id: "p-c",
              name: "Cavendish National Park",
              feature_type: "national_park",
              dataset: "mock",
              lon: -63.39,
              lat: 46.5,
              score: 0.998,
              population: null,
              region: "Prince Edward Island, Canada",
            },
          ];
      return json(route, { query, results });
    }

    return json(route, { detail: `Unhandled mock request: ${method} ${pathname}` }, 500);
  });

  return {
    getTrip: () => trip,
    isDeleted: () => deleted,
    getStopReplacementRequestCount: () => stopReplacementRequests,
  };
}
