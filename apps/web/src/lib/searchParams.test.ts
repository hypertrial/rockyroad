import { describe, expect, it } from "vitest";
import { validatePlannerSearch } from "./searchParams";

describe("validatePlannerSearch", () => {
  it("keeps finite viewport state and known panels", () => {
    expect(
      validatePlannerSearch({
        lat: "46.238",
        lng: "-63.131",
        z: "8.25",
        stop: "abc",
        panel: "directions",
      }),
    ).toEqual({
      lat: 46.238,
      lng: -63.131,
      z: 8.25,
      stop: "abc",
      panel: "directions",
    });
  });

  it("drops invalid values", () => {
    expect(
      validatePlannerSearch({ lat: "999", lng: "-181", panel: "satellite", z: "23" }),
    ).toEqual({});
    expect(validatePlannerSearch({ lat: "nope", z: "NaN" })).toEqual({});
  });

  it("keeps camera boundary values", () => {
    expect(validatePlannerSearch({ lat: "-90", lng: "180", z: "22" })).toEqual({
      lat: -90,
      lng: 180,
      z: 22,
    });
  });
});
