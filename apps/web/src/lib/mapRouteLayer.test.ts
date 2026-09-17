import { describe, expect, it, vi } from "vitest";
import {
  EMPTY_ROUTE_GEOMETRY,
  TRIP_ROUTE_HALO_LAYER_ID,
  TRIP_ROUTE_LAYER_ID,
  TRIP_ROUTE_SOURCE_ID,
  syncTripRouteLayer,
} from "./mapRouteLayer";

function fakeMap(options?: { loaded?: boolean; hasSource?: boolean }) {
  const setData = vi.fn();
  const addSource = vi.fn();
  const addLayer = vi.fn();
  return {
    setData,
    addSource,
    addLayer,
    map: {
      isStyleLoaded: () => options?.loaded ?? false,
      getSource: (id: string) => (options?.hasSource && id === TRIP_ROUTE_SOURCE_ID ? { setData } : undefined),
      addSource,
      addLayer,
    },
  };
}

const geometry = {
  type: "LineString" as const,
  coordinates: [
    [-63.13, 46.24],
    [-63.79, 46.39],
  ],
};

describe("syncTripRouteLayer", () => {
  it("skips painting until the style is loaded", () => {
    const { map, addSource, addLayer } = fakeMap({ loaded: false });
    expect(syncTripRouteLayer(map, geometry)).toBe(false);
    expect(addSource).not.toHaveBeenCalled();
    expect(addLayer).not.toHaveBeenCalled();
  });

  it("adds the cached route after the style loads", () => {
    const { map, addSource, addLayer } = fakeMap({ loaded: true });
    expect(syncTripRouteLayer(map, geometry)).toBe(true);
    expect(addSource).toHaveBeenCalledWith(
      TRIP_ROUTE_SOURCE_ID,
      expect.objectContaining({
        type: "geojson",
        data: expect.objectContaining({ geometry }),
      }),
    );
    expect(addLayer).toHaveBeenNthCalledWith(1, expect.objectContaining({ id: TRIP_ROUTE_HALO_LAYER_ID }));
    expect(addLayer).toHaveBeenNthCalledWith(2, expect.objectContaining({ id: TRIP_ROUTE_LAYER_ID }));
  });

  it("updates an existing source instead of adding another layer", () => {
    const { map, setData, addSource, addLayer } = fakeMap({ loaded: true, hasSource: true });
    expect(syncTripRouteLayer(map, geometry)).toBe(true);
    expect(setData).toHaveBeenCalledWith(expect.objectContaining({ geometry }));
    expect(addSource).not.toHaveBeenCalled();
    expect(addLayer).not.toHaveBeenCalled();
  });

  it("paints an empty line when the trip has no route yet", () => {
    const { map, addSource } = fakeMap({ loaded: true });
    syncTripRouteLayer(map, null);
    expect(addSource).toHaveBeenCalledWith(
      TRIP_ROUTE_SOURCE_ID,
      expect.objectContaining({
        data: expect.objectContaining({ geometry: EMPTY_ROUTE_GEOMETRY }),
      }),
    );
  });
});
