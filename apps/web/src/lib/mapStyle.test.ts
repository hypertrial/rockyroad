import { describe, expect, it } from "vitest";
import {
  EMPTY_MAP_STYLE,
  LOCAL_TILE_STYLE,
  OPENFREEMAP_STYLE,
  mapLoadFailure,
  plannerMapStyle,
  usesLocalPmtiles,
} from "./mapStyle";

describe("plannerMapStyle", () => {
  it("skips PMTiles when the local basemap is missing", () => {
    expect(plannerMapStyle({ maps: false, provider_mode: "local", map_style_url: null })).toEqual(EMPTY_MAP_STYLE);
    expect(JSON.stringify(plannerMapStyle({ maps: false, provider_mode: "local", map_style_url: null }))).not.toContain(
      "pmtiles",
    );
  });

  it("uses the offline style file when tiles exist", () => {
    expect(plannerMapStyle({ maps: true, provider_mode: "local", map_style_url: "/map/style.json" })).toBe(
      LOCAL_TILE_STYLE,
    );
  });

  it("uses the OpenFreeMap style URL in hosted mode", () => {
    expect(
      plannerMapStyle({
        maps: true,
        provider_mode: "hosted",
        map_style_url: OPENFREEMAP_STYLE,
      }),
    ).toBe(OPENFREEMAP_STYLE);
    expect(usesLocalPmtiles({ maps: true, provider_mode: "hosted" })).toBe(false);
    expect(usesLocalPmtiles({ maps: true, provider_mode: "local" })).toBe(true);
  });
});

describe("mapLoadFailure", () => {
  it("reports fatal HTTP and network failures", () => {
    expect(mapLoadFailure({ status: 500 })).toMatch(/temporarily unavailable/);
    expect(mapLoadFailure({ message: "Failed to fetch style" })).toMatch(/temporarily unavailable/);
  });

  it("ignores noncritical resource and unrelated errors", () => {
    expect(mapLoadFailure({ status: 404, message: "Missing sprite image" })).toBeNull();
    expect(mapLoadFailure({ message: "WebGL warning" })).toBeNull();
  });
});
