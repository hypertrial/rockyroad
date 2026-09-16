import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Trip } from "../lib/types";
import { StopList } from "./StopList";

const trip: Trip = {
  id: "trip-1",
  name: "Island",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  settings: {
    trip_id: "trip-1",
    avoid_tolls: false,
    avoid_highways: false,
    avoid_ferries: false,
    costing: "auto",
    optimize: false,
    selected_alternative: 0,
    updated_at: "2026-01-01T00:00:00Z",
  },
  route: null,
  stops: [
    {
      id: "a",
      trip_id: "trip-1",
      position: 0,
      name: "Charlottetown",
      lon: -63.13,
      lat: 46.24,
      place_id: null,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "b",
      trip_id: "trip-1",
      position: 1,
      name: "Summerside",
      lon: -63.79,
      lat: 46.39,
      place_id: null,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
};

describe("StopList", () => {
  it("reorders and removes stops", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<StopList trip={trip} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Move Summerside up" }));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ name: "Summerside" }),
      expect.objectContaining({ name: "Charlottetown" }),
    ]);
    await user.click(screen.getByRole("button", { name: "Remove Charlottetown" }));
    expect(onChange).toHaveBeenLastCalledWith([expect.objectContaining({ name: "Summerside" })]);
  });
});
