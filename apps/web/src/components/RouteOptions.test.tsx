import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Trip } from "../lib/types";
import { RouteOptions } from "./RouteOptions";

afterEach(cleanup);

const trip: Trip = {
  id: "trip-1",
  name: "Coastal loop",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  stops: [],
  route: null,
  settings: {
    trip_id: "trip-1",
    avoid_tolls: true,
    avoid_highways: false,
    avoid_ferries: false,
    costing: "auto",
    optimize: false,
    selected_alternative: 0,
    updated_at: "2026-01-01T00:00:00Z",
  },
};

describe("RouteOptions", () => {
  it("renders current values and reports the exact setting changed", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<RouteOptions trip={trip} onToggle={onToggle} />);

    expect(screen.getByRole("checkbox", { name: /Avoid tolls/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Avoid highways/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Avoid ferries/ })).not.toBeChecked();

    await user.click(screen.getByRole("checkbox", { name: /Avoid highways/ }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith("avoid_highways");
  });

  it("prevents duplicate writes while a settings mutation is pending", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<RouteOptions trip={trip} disabled onToggle={onToggle} />);

    const toggles = screen.getAllByRole("checkbox");
    expect(toggles).toHaveLength(3);
    toggles.forEach((toggle) => expect(toggle).toBeDisabled());
    await user.click(toggles[0]);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("announces persistence failures without losing the current values", () => {
    render(<RouteOptions trip={trip} error="Could not save route preferences." onToggle={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Could not save route preferences.");
    expect(screen.getByRole("checkbox", { name: /Avoid tolls/ })).toBeChecked();
  });
});
