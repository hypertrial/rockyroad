import { describe, expect, it } from "vitest";
import { EMPTY_MAP_STYLE, LOCAL_TILE_STYLE, OPENFREEMAP_STYLE, plannerMapStyle, usesLocalPmtiles } from "./mapStyle";

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
