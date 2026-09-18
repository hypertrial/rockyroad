import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Trip } from "../lib/types";
import { StopList } from "./StopList";

afterEach(cleanup);

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
      place_id: "place-a",
      created_at: "2026-01-01T00:00:00Z",
      region: "Prince Edward Island, Canada",
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
      region: null,
    },
  ],
};

function renderStops(overrides: Partial<ComponentProps<typeof StopList>> = {}) {
  const props: ComponentProps<typeof StopList> = {
    trip,
    selectedStopId: null,
    onChange: vi.fn(),
    onSelect: vi.fn(),
    onReplace: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<StopList {...props} />) };
}

describe("StopList", () => {
  it("marks the selected stop and makes every stop map-focusable", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderStops({ selectedStopId: "a", onSelect });

    expect(screen.getByRole("button", { name: /Charlottetown Prince Edward Island, Canada/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Summerside 46\.390/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await user.click(screen.getByRole("button", { name: /Summerside 46\.390/ }));
    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("enforces reorder boundaries and emits the complete reordered stop list", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderStops({ onChange });

    expect(screen.getByRole("button", { name: "Move Charlottetown up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Summerside down" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Move Summerside up" }));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith([
      {
        id: "b",
        name: "Summerside",
        lon: -63.79,
        lat: 46.39,
        place_id: null,
        region: null,
      },
      {
        id: "a",
        name: "Charlottetown",
        lon: -63.13,
        lat: 46.24,
        place_id: "place-a",
        region: "Prince Edward Island, Canada",
      },
    ]);
  });

  it("offers explicit keyboard-accessible location replacement and removal", async () => {
    const user = userEvent.setup();
    const onReplace = vi.fn();
    const onRemove = vi.fn();
    renderStops({ onReplace, onRemove });

    await user.click(screen.getByRole("button", { name: "Change location for Charlottetown" }));
    await user.click(screen.getByRole("button", { name: "Remove Summerside" }));
    expect(onReplace).toHaveBeenCalledWith("a");
    expect(onRemove).toHaveBeenCalledWith("b");
  });

  it("locks every stop mutation control while persistence is pending", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onReplace = vi.fn();
    const onRemove = vi.fn();
    renderStops({ disabled: true, onChange, onReplace, onRemove });

    for (const button of screen.getAllByRole("button", { name: /^(Reorder|Move|Change location|Remove)/ })) {
      expect(button).toBeDisabled();
    }
    await user.click(screen.getByRole("button", { name: "Move Summerside up" }));
    await user.click(screen.getByRole("button", { name: "Change location for Summerside" }));
    await user.click(screen.getByRole("button", { name: "Remove Summerside" }));
    expect(onChange).not.toHaveBeenCalled();
    expect(onReplace).not.toHaveBeenCalled();
    expect(onRemove).not.toHaveBeenCalled();
  });

  it("shows a persisted region instead of coordinates when one is present", () => {
    renderStops();

    expect(screen.getByText("Prince Edward Island, Canada")).toBeInTheDocument();
    expect(screen.getByText("46.390, -63.790")).toBeInTheDocument();
    expect(screen.queryByText("46.240, -63.130")).not.toBeInTheDocument();
  });

  it("renders actionable empty-state guidance for a new trip", () => {
    renderStops({ trip: { ...trip, stops: [] } });

    expect(screen.getByText("Add your first stop")).toBeInTheDocument();
    expect(screen.getByText(/Search for a place or click anywhere/)).toBeInTheDocument();
    expect(screen.getByLabelText("0 stops")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
