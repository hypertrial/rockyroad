import { afterEach, describe, expect, it, vi } from "vitest";
import { api, formatApiErrorDetail, formatRoutingError } from "./api";

describe("formatApiErrorDetail", () => {
  it("joins FastAPI 422 detail arrays", () => {
    expect(
      formatApiErrorDetail([
        { loc: ["body", "name"], msg: "String should have at least 1 character", type: "string_too_short" },
        { loc: ["body", "stops"], msg: "Field required", type: "missing" },
      ]),
    ).toBe("String should have at least 1 character; Field required");
  });

  it("returns string details unchanged", () => {
    expect(formatApiErrorDetail("trip not found")).toBe("trip not found");
  });
});

describe("formatRoutingError", () => {
  it("explains Valhalla 171 errors for the sample extract", () => {
    expect(
      formatRoutingError(
        'routing data could not produce a path (400): {"error_code":171,"error":"No suitable edges near location"}',
        "sample",
      ),
    ).toMatch(/Prince Edward Island/);
  });

  it("keeps continental 171 errors profile-neutral", () => {
    expect(
      formatRoutingError(
        'routing data could not produce a path (400): {"error_code":171,"error":"No suitable edges near location"}',
        "canada-usa",
      ),
    ).toMatch(/canada-usa/);
    expect(
      formatRoutingError(
        'routing data could not produce a path (400): {"error_code":171,"error":"No suitable edges near location"}',
        "canada-usa",
      ),
    ).not.toMatch(/Prince Edward Island/);
  });

  it("leaves other routing errors unchanged", () => {
    expect(formatRoutingError("Valhalla routing service is unavailable")).toBe(
      "Valhalla routing service is unavailable",
    );
  });

  it("does not assume PEI when the profile is unknown", () => {
    expect(
      formatRoutingError(
        'routing data could not produce a path (400): {"error_code":171,"error":"No suitable edges near location"}',
      ),
    ).toBe("No roads near those stops in the local Valhalla graph.");
  });
});

describe("api errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws a readable message for FastAPI 422 lists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: async () => ({
          detail: [{ loc: ["body", "name"], msg: "String should have at least 1 character", type: "string_too_short" }],
        }),
      }),
    );
    await expect(api.createTrip("")).rejects.toThrow("String should have at least 1 character");
  });
});
