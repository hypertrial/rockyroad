import { describe, expect, it } from "vitest";
import { formatDistance, formatDuration } from "./format";

describe("formatters", () => {
  it("formats distances and durations", () => {
    expect(formatDistance(240)).toBe("240 m");
    expect(formatDistance(12340)).toBe("12.3 km");
    expect(formatDuration(90)).toBe("2 min");
    expect(formatDuration(3720)).toBe("1 h 2 min");
  });
});
