import { describe, expect, it } from "vitest";
import type { Stop } from "./types";
import { commitMapPoint, coverageDropHint, toStopDrafts, withMovedStop } from "./mapInteraction";

const pei = [-64.45, 45.9, -61.9, 47.1];
const [west, south, east, north] = pei;
const midLon = -63.175;
const midLat = 46.5;

const twoStops = [
  { id: "a", name: "Charlottetown", lon: -63.13, lat: 46.24, place_id: "place-a" },
  { id: "b", name: "Summerside", lon: -63.79, lat: 46.39, place_id: "place-b" },
];

describe("commitMapPoint", () => {
  it("keeps points inside coverage", () => {
    expect(commitMapPoint(-63.13, 46.24, pei)).toEqual({ ok: true, lon: -63.13, lat: 46.24 });
  });

  it("accepts inclusive extract edges and corners", () => {
    expect(commitMapPoint(west, midLat, pei)).toEqual({ ok: true, lon: west, lat: midLat });
    expect(commitMapPoint(east, midLat, pei)).toEqual({ ok: true, lon: east, lat: midLat });
    expect(commitMapPoint(midLon, south, pei)).toEqual({ ok: true, lon: midLon, lat: south });
    expect(commitMapPoint(midLon, north, pei)).toEqual({ ok: true, lon: midLon, lat: north });
    expect(commitMapPoint(west, south, pei)).toEqual({ ok: true, lon: west, lat: south });
    expect(commitMapPoint(west, north, pei)).toEqual({ ok: true, lon: west, lat: north });
    expect(commitMapPoint(east, south, pei)).toEqual({ ok: true, lon: east, lat: south });
    expect(commitMapPoint(east, north, pei)).toEqual({ ok: true, lon: east, lat: north });
  });

  it("rejects points just outside extract edges", () => {
    expect(commitMapPoint(west - 0.0001, midLat, pei)).toEqual({ ok: false });
    expect(commitMapPoint(east + 0.0001, midLat, pei)).toEqual({ ok: false });
    expect(commitMapPoint(midLon, south - 0.0001, pei)).toEqual({ ok: false });
    expect(commitMapPoint(midLon, north + 0.0001, pei)).toEqual({ ok: false });
  });

  it("rejects points outside coverage", () => {
    expect(commitMapPoint(-114.07, 51.05, pei)).toEqual({ ok: false });
  });

  it("rejects NaN and non-finite coordinates when coverage bounds exist", () => {
    expect(commitMapPoint(Number.NaN, midLat, pei)).toEqual({ ok: false });
    expect(commitMapPoint(midLon, Number.NaN, pei)).toEqual({ ok: false });
    expect(commitMapPoint(Number.NaN, Number.NaN, pei)).toEqual({ ok: false });
    expect(commitMapPoint(Number("not-a-coord"), 46.24, pei)).toEqual({ ok: false });
    expect(commitMapPoint(Number.POSITIVE_INFINITY, midLat, pei)).toEqual({ ok: false });
    expect(commitMapPoint(midLon, Number.NEGATIVE_INFINITY, pei)).toEqual({ ok: false });
  });

  it("rejects non-finite coordinates even when bounds are missing", () => {
    expect(commitMapPoint(Number.NaN, 46.24, null)).toEqual({ ok: false });
    expect(commitMapPoint(-63.13, Number.POSITIVE_INFINITY, null)).toEqual({ ok: false });
  });
});

describe("withMovedStop", () => {
  it("updates one stop and clears its place id", () => {
    expect(withMovedStop(twoStops, "b", -63.5, 46.3)).toEqual([
      { id: "a", name: "Charlottetown", lon: -63.13, lat: 46.24, place_id: "place-a" },
      { id: "b", name: "Summerside", lon: -63.5, lat: 46.3, place_id: null },
    ]);
  });

  it("changes only the moved stop among several", () => {
    const stops = [
      ...twoStops,
      { id: "c", name: "Cavendish", lon: -63.43, lat: 46.49, place_id: "place-c" },
    ];
    const moved = withMovedStop(stops, "a", -63.2, 46.3);

    expect(moved).toHaveLength(3);
    expect(moved[0]).toEqual({ id: "a", name: "Charlottetown", lon: -63.2, lat: 46.3, place_id: null });
    expect(moved[1]).toEqual(stops[1]);
    expect(moved[2]).toEqual(stops[2]);
    expect(moved[1]).toBe(stops[1]);
    expect(moved[2]).toBe(stops[2]);
  });

  it("leaves stops unchanged when the id is unknown", () => {
    const original = twoStops.map((stop) => ({ ...stop }));
    const result = withMovedStop(original, "missing", -63.5, 46.3);

    expect(result).toEqual(original);
    expect(result.every((stop, index) => stop === original[index])).toBe(true);
  });

  it("returns an empty list when there are no stops", () => {
    expect(withMovedStop([], "a", -63.5, 46.3)).toEqual([]);
  });

  it("does not mutate the original stops array", () => {
    const stops = twoStops.map((stop) => ({ ...stop }));
    const snapshot = structuredClone(stops);

    withMovedStop(stops, "a", -63.2, 46.3);

    expect(stops).toEqual(snapshot);
  });

  it("copies persisted stops into replace-stops drafts", () => {
    const stop: Stop = {
      id: "a",
      trip_id: "trip-1",
      position: 0,
      name: "Calgary",
      lon: -114.07,
      lat: 51.04,
      place_id: "place-a",
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(toStopDrafts([stop])).toEqual([{ id: "a", name: "Calgary", lon: -114.07, lat: 51.04, place_id: "place-a" }]);
  });
});

describe("coverageDropHint", () => {
  it("names the hosted coverage", () => {
    expect(coverageDropHint("canada-usa", "hosted")).toBe(
      "Drop the pin inside the map coverage. Stay inside Canada and the USA.",
    );
  });

  it("uses local extract wording instead of hosted Canada/USA copy", () => {
    expect(coverageDropHint("sample", "local")).toBe(
      "Drop the pin inside the map coverage. With the sample extract, stay on Prince Edward Island.",
    );
    expect(coverageDropHint("canada-usa", "local")).toBe(
      "Drop the pin inside the map coverage. Stay inside the canada-usa extract.",
    );
    expect(coverageDropHint("sample", "local")).not.toMatch(/Canada and the USA/);
    expect(coverageDropHint("canada-usa", "local")).not.toMatch(/Canada and the USA/);
    expect(coverageDropHint("canada-usa", "local")).not.toMatch(/Prince Edward Island/);
  });

  it("keeps the drop prefix when there is no extra coverage hint", () => {
    expect(coverageDropHint(undefined)).toBe("Drop the pin inside the map coverage.");
    expect(coverageDropHint(null, "local")).toBe("Drop the pin inside the map coverage.");
  });
});
