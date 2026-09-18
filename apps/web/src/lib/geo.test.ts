import { describe, expect, it } from "vitest";
import { haversineMeters, viewportCenter } from "./geo";

describe("haversineMeters", () => {
  it("returns zero for the same point", () => {
    expect(haversineMeters(-123.12, 49.26, -123.12, 49.26)).toBeCloseTo(0, 5);
  });

  it("measures Vancouver BC to Vancouver WA at a few hundred kilometers", () => {
    const meters = haversineMeters(-123.1139, 49.2609, -122.675, 45.6307);
    expect(meters).toBeGreaterThan(350_000);
    expect(meters).toBeLessThan(500_000);
  });

  it("matches a two-kilometer north offset at the same radius as the API", () => {
    const latDelta = (2 / 6371) * (180 / Math.PI);
    const meters = haversineMeters(-114.071, 51.045, -114.071, 51.045 + latDelta);
    expect(meters).toBeCloseTo(2_000, 0);
    expect(haversineMeters(-114.071, 51.045 + latDelta, -114.071, 51.045)).toBeCloseTo(meters, 5);
  });
});

describe("viewportCenter", () => {
  it("returns null without a viewport", () => {
    expect(viewportCenter(null)).toBeNull();
    expect(viewportCenter(undefined)).toBeNull();
  });

  it("averages the four bounds", () => {
    expect(viewportCenter({ west: -124, south: 48, east: -122, north: 50 })).toEqual({ lon: -123, lat: 49 });
  });

  it("keeps the center inside an antimeridian wrap", () => {
    const center = viewportCenter({ west: 170, south: 50, east: -170, north: 55 });
    expect(center).not.toBeNull();
    expect(center?.lat).toBe(52.5);
    expect(Math.abs(center?.lon ?? 0)).toBeGreaterThanOrEqual(170);
    expect(center?.lon).not.toBe(0);
  });

  it("places an asymmetric wrap center in the negative hemisphere", () => {
    expect(viewportCenter({ west: 170, south: 50, east: -160, north: 55 })).toEqual({
      lon: -175,
      lat: 52.5,
    });
  });

  it("places an asymmetric wrap center in the positive hemisphere", () => {
    expect(viewportCenter({ west: 160, south: 50, east: -170, north: 55 })).toEqual({
      lon: 175,
      lat: 52.5,
    });
  });
});
