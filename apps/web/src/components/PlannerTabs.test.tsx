import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlannerPanel } from "./PlannerTabs";
import { PlannerTabs } from "./PlannerTabs";

afterEach(cleanup);

function ControlledTabs({ onChange = vi.fn() }: { onChange?: (panel: PlannerPanel) => void }) {
  const [active, setActive] = useState<PlannerPanel>("stops");
  return (
    <PlannerTabs
      active={active}
      onChange={(panel) => {
        setActive(panel);
        onChange(panel);
      }}
    />
  );
}

describe("PlannerTabs", () => {
  it("exposes one selected, tabbable tab with stable panel associations", () => {
    render(<PlannerTabs active="stops" onChange={vi.fn()} />);

    expect(screen.getByRole("tablist", { name: "Trip planning tools" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Stops", selected: true })).toHaveAttribute(
      "aria-controls",
      "planner-tabpanel",
    );
    expect(screen.getByRole("tab", { name: "Stops" })).toHaveAttribute("tabindex", "0");
    for (const name of ["Search", "Route", "Directions"]) {
      expect(screen.getByRole("tab", { name })).toHaveAttribute("tabindex", "-1");
    }
  });

  it("moves selection and focus with arrow keys, including wraparound", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ControlledTabs onChange={onChange} />);

    const stops = screen.getByRole("tab", { name: "Stops" });
    stops.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Route", selected: true })).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith("options");

    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("tab", { name: "Stops", selected: true })).toHaveFocus();

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Search", selected: true })).toHaveFocus();

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Directions", selected: true })).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith("directions");
  });

  it("supports Home and End without hijacking unrelated keys", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ControlledTabs onChange={onChange} />);

    const stops = screen.getByRole("tab", { name: "Stops" });
    stops.focus();
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Directions", selected: true })).toHaveFocus();

    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Search", selected: true })).toHaveFocus();

    const calls = onChange.mock.calls.length;
    await user.keyboard("x");
    expect(onChange).toHaveBeenCalledTimes(calls);
    expect(screen.getByRole("tab", { name: "Search", selected: true })).toHaveFocus();
  });

  it("activates a clicked tab", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<PlannerTabs active="search" onChange={onChange} />);

    await user.click(screen.getByRole("tab", { name: "Directions" }));
    expect(onChange).toHaveBeenCalledWith("directions");
  });
});
