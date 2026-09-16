import { afterEach, describe, expect, it, vi } from "vitest";
import { api, formatApiErrorDetail } from "./api";

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
