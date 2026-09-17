import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RouteAlternative, Trip } from "../lib/types";
import { Directions } from "./Directions";

afterEach(cleanup);

const alternatives: RouteAlternative[] = [
  {
    index: 0,
    distance_m: 120_000,
    duration_s: 5_400,
    geometry: { type: "LineString", coordinates: [[-63, 46], [-64, 47]] },
    maneuvers: [
      {
        instruction: "Head north on Pine Road",
        type: 1,
        distance_m: 800,
        duration_s: 90,
        begin_shape_index: 0,
      },
      {
        instruction: "Turn left toward the coast",
        type: 2,
        distance_m: 12_400,
        duration_s: 600,
        begin_shape_index: 4,
      },
    ],
  },
  {
    index: 1,
    distance_m: 98_500,
    duration_s: 6_300,
    geometry: { type: "LineString", coordinates: [[-63, 46], [-62, 47]] },
    maneuvers: [
      {
        instruction: "Take the ferry approach",
        type: 3,
        distance_m: 1_500,
        duration_s: 180,
        begin_shape_index: 0,
      },
    ],
  },
];

function makeTrip(selectedAlternative = 0, route = true): Trip {
  return {
    id: "trip-1",
    name: "Coastal loop",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    stops: [],
    route: route
      ? { trip_id: "trip-1", cache_hit: false, data_version: "test-v1", alternatives }
      : null,
    settings: {
      trip_id: "trip-1",
      avoid_tolls: false,
      avoid_highways: false,
      avoid_ferries: false,
      costing: "auto",
      optimize: false,
      selected_alternative: selectedAlternative,
      updated_at: "2026-01-01T00:00:00Z",
    },
  };
}

describe("Directions", () => {
  it("provides clear guidance before a route exists", () => {
    render(<Directions trip={makeTrip(0, false)} onSelectAlternative={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Directions will appear here" })).toBeInTheDocument();
    expect(screen.getByText(/Add at least two stops/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Route alternatives")).not.toBeInTheDocument();
  });

  it("presents route alternatives as exclusive choices and updates selection", async () => {
    const user = userEvent.setup();
    const onSelectAlternative = vi.fn();
    render(<Directions trip={makeTrip(1)} onSelectAlternative={onSelectAlternative} />);

    const primary = screen.getByRole("button", { name: /Route 1/ });
    const alternate = screen.getByRole("button", { name: /Route 2/ });
    expect(primary).toHaveAttribute("aria-pressed", "false");
    expect(alternate).toHaveAttribute("aria-pressed", "true");
    expect(alternate).toHaveTextContent("1 h 45 min");
    expect(alternate).toHaveTextContent("98.5 km");
    expect(screen.getByText("Take the ferry approach")).toBeInTheDocument();
    expect(screen.queryByText("Head north on Pine Road")).not.toBeInTheDocument();

    await user.click(primary);
    expect(onSelectAlternative).toHaveBeenCalledWith(0);
  });

  it("falls back safely when persisted selection no longer exists", () => {
    render(<Directions trip={makeTrip(99)} onSelectAlternative={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Route 1/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Head north on Pine Road")).toBeInTheDocument();
  });

  it("locks alternative changes while pending and announces failures", async () => {
    const user = userEvent.setup();
    const onSelectAlternative = vi.fn();
    render(
      <Directions
        trip={makeTrip()}
        disabled
        error="Could not select that route."
        onSelectAlternative={onSelectAlternative}
      />,
    );

    const alternatives = screen.getAllByRole("button");
    alternatives.forEach((alternative) => expect(alternative).toBeDisabled());
    expect(screen.getByRole("alert")).toHaveTextContent("Could not select that route.");
    await user.click(alternatives[1]);
    expect(onSelectAlternative).not.toHaveBeenCalled();
  });
});
