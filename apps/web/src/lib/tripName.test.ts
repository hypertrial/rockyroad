import { describe, expect, it } from "vitest";
import { shouldPersistTripName } from "./tripName";

describe("shouldPersistTripName", () => {
  it("saves a changed non-empty name", () => {
    expect(shouldPersistTripName("Cabot loop", "New road trip")).toBe(true);
  });

  it("ignores whitespace-only and unchanged names", () => {
    expect(shouldPersistTripName("   ", "Island")).toBe(false);
    expect(shouldPersistTripName("Island  ", "Island")).toBe(false);
  });
});
