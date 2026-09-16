import { describe, expect, it } from "vitest";
import { EMPTY_MAP_STYLE, LOCAL_TILE_STYLE, plannerMapStyle } from "./mapStyle";

describe("plannerMapStyle", () => {
  it("skips PMTiles when the local basemap is missing", () => {
    expect(plannerMapStyle(false)).toEqual(EMPTY_MAP_STYLE);
    expect(JSON.stringify(plannerMapStyle(false))).not.toContain("pmtiles");
  });

  it("uses the offline style file when tiles exist", () => {
    expect(plannerMapStyle(true)).toBe(LOCAL_TILE_STYLE);
  });
});
