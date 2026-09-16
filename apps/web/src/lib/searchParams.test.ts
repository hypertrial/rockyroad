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
    expect(validatePlannerSearch({ lat: "nope", panel: "satellite", z: "NaN" })).toEqual({});
  });
});
