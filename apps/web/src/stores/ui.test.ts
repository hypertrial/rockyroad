import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "./ui";

describe("ui store", () => {
  beforeEach(() => {
    useUiStore.setState({
      selectedStopId: null,
      panel: "stops",
      hoveredManeuverIndex: null,
      mapReady: false,
      viewport: null,
    });
  });

  it("only holds ephemeral planner chrome", () => {
    useUiStore.getState().setPanel("search");
    useUiStore.getState().setSelectedStopId("stop-1");
    expect(useUiStore.getState().panel).toBe("search");
    expect(useUiStore.getState().selectedStopId).toBe("stop-1");
  });
});
