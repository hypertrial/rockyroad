import { create } from "zustand";

type Panel = "search" | "stops" | "directions" | "options";

export type ViewportBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
};

type UiState = {
  selectedStopId: string | null;
  panel: Panel;
  hoveredManeuverIndex: number | null;
  mapReady: boolean;
  viewport: ViewportBounds | null;
  setSelectedStopId: (id: string | null) => void;
  setPanel: (panel: Panel) => void;
  setHoveredManeuverIndex: (index: number | null) => void;
  setMapReady: (ready: boolean) => void;
  setViewport: (viewport: ViewportBounds) => void;
};

export const useUiStore = create<UiState>((set) => ({
  selectedStopId: null,
  panel: "stops",
  hoveredManeuverIndex: null,
  mapReady: false,
  viewport: null,
  setSelectedStopId: (selectedStopId) => set({ selectedStopId }),
  setPanel: (panel) => set({ panel }),
  setHoveredManeuverIndex: (hoveredManeuverIndex) => set({ hoveredManeuverIndex }),
  setMapReady: (mapReady) => set({ mapReady }),
  setViewport: (viewport) => set({ viewport }),
}));
