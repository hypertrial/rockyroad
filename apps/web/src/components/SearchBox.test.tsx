import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { HealthResponse, PlaceResult, SearchResponse } from "../lib/types";
import { SearchBox } from "./SearchBox";

const hosted: HealthResponse = {
  status: "ok",
  duckdb: true,
  geo: true,
  routing: true,
  maps: true,
  data_version: "ors-v1",
  detail: null,
  bounds: [-168, 24, -52, 83.5],
  profile: "canada-usa",
  provider_mode: "hosted",
  map_style_url: "https://tiles.openfreemap.org/styles/liberty",
  map_provider: "openfreemap",
  routing_provider: "openrouteservice",
  search_provider: "photon",
};

const banff: PlaceResult = {
  id: "banff",
  name: "Banff National Park",
  feature_type: "national_park",
  dataset: "places",
  lon: -115.57,
  lat: 51.18,
  score: 847.234,
  population: null,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const vancouverBc: PlaceResult = {
  id: "photon:N:bc",
  name: "Vancouver",
  feature_type: "city",
  dataset: "photon",
  lon: -123.11,
  lat: 49.26,
  score: 1,
  population: null,
  state: "British Columbia",
  country: "Canada",
  country_code: "CA",
  place_type: "city",
  region: "British Columbia, Canada",
};

const vancouverWa: PlaceResult = {
  id: "photon:N:wa",
  name: "Vancouver",
  feature_type: "city",
  dataset: "photon",
  lon: -122.67,
  lat: 45.63,
  score: 0.98,
  population: null,
  state: "Washington",
  country: "United States",
  country_code: "US",
  place_type: "city",
  region: "Washington, United States",
};

const nearVancouver: { west: number; south: number; east: number; north: number } = {
  west: -123.2,
  south: 49.2,
  east: -123.0,
  north: 49.3,
};

function renderSearch({
  health = hosted,
  onSelect = vi.fn(),
  onPreview,
  viewport = null,
  disabled = false,
  editingName = null,
}: {
  health?: HealthResponse;
  onSelect?: (place: PlaceResult) => void | Promise<void>;
  onPreview?: (place: PlaceResult | null) => void;
  viewport?: { west: number; south: number; east: number; north: number } | null;
  disabled?: boolean;
  editingName?: string | null;
} = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return {
    onSelect,
    ...render(
      <QueryClientProvider client={client}>
        <SearchBox
          onSelect={onSelect}
          onPreview={onPreview}
          health={health}
          viewport={viewport}
          disabled={disabled}
          editingName={editingName}
        />
      </QueryClientProvider>,
    ),
  };
}

describe("SearchBox", () => {
  it("waits for a meaningful query and announces an in-flight hosted search", async () => {
    const user = userEvent.setup();
    const pending = new Promise<SearchResponse>(() => undefined);
    const search = vi.spyOn(api, "search").mockReturnValue(pending);
    renderSearch();

    await user.type(screen.getByRole("searchbox", { name: "Search places" }), "b");
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    expect(search).not.toHaveBeenCalled();

    await user.type(screen.getByRole("searchbox", { name: "Search places" }), "a");
    expect(await screen.findByText("Searching places…", {}, { timeout: 1_000 })).toBeInTheDocument();
    await waitFor(() => expect(search).toHaveBeenCalledTimes(1));
    expect(search).toHaveBeenCalledWith("ba", undefined);
  });

  it("shows human-readable place metadata, never the internal score, and selects the result", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "search").mockResolvedValue({ query: "banff", results: [banff] });
    const onSelect = vi.fn();
    renderSearch({ onSelect });

    await user.type(screen.getByRole("searchbox"), "banff");
    const name = await screen.findByText("Banff National Park", {}, { timeout: 1_000 });
    const result = name.closest("button");
    expect(result).not.toBeNull();
    expect(within(result as HTMLButtonElement).getByText("National Park")).toBeInTheDocument();
    expect(within(result as HTMLButtonElement).getByText("51.18, -115.57")).toBeInTheDocument();
    expect(screen.queryByText("847.234")).not.toBeInTheDocument();

    await user.click(result as HTMLButtonElement);
    expect(onSelect).toHaveBeenCalledWith(banff);
  });

  it("clears the field and restores useful empty guidance", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "search").mockResolvedValue({ query: "banff", results: [banff] });
    renderSearch();

    const input = screen.getByRole("searchbox");
    await user.type(input, "banff");
    expect(await screen.findByText("Banff National Park", {}, { timeout: 1_000 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));

    expect(input).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
    expect(screen.getByText(/Try a city, park, campground/)).toBeInTheDocument();
    expect(screen.queryByText("Banff National Park")).not.toBeInTheDocument();
  });

  it("hides placeholder results as soon as the visible query changes", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "search")
      .mockResolvedValueOnce({ query: "banff", results: [banff] })
      .mockReturnValueOnce(new Promise<SearchResponse>(() => undefined));
    renderSearch();

    const input = screen.getByRole("searchbox");
    await user.type(input, "banff");
    expect(await screen.findByText("Banff National Park", {}, { timeout: 1_000 })).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "jasper");

    expect(screen.queryByText("Banff National Park")).not.toBeInTheDocument();
  });

  it("offers a working retry after a provider failure", async () => {
    const user = userEvent.setup();
    const search = vi
      .spyOn(api, "search")
      .mockRejectedValueOnce(new Error("quota exhausted"))
      .mockResolvedValueOnce({ query: "banff", results: [] });
    renderSearch();

    await user.type(screen.getByRole("searchbox"), "banff");
    expect(await screen.findByRole("alert", {}, { timeout: 1_000 })).toHaveTextContent(
      "Search quota or rate limit reached",
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("No places found")).toBeInTheDocument();
    expect(search).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("distinguishes same-name results by region and shows distance when a viewport exists", async () => {
    const user = userEvent.setup();
    const search = vi.spyOn(api, "search").mockResolvedValue({ query: "vancouver", results: [vancouverBc, vancouverWa] });
    renderSearch({ viewport: nearVancouver });

    await user.type(screen.getByRole("searchbox"), "vancouver");
    await screen.findByText(/British Columbia, Canada/, {}, { timeout: 1_000 });
    expect(search).toHaveBeenCalledWith("vancouver", nearVancouver);
    const rows = screen.getAllByRole("button").filter((button) => button.textContent?.includes("Vancouver"));
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("City · British Columbia, Canada");
    expect(rows[1]).toHaveTextContent("City · Washington, United States");
    expect(rows[0]).toHaveTextContent("km");
    expect(rows[0]).not.toHaveTextContent("49.26, -123.11");
    expect(rows[1]).not.toHaveTextContent("45.63, -122.67");
  });

  it("falls back to coordinates without a viewport and previews the focused result", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "search").mockResolvedValue({ query: "vancouver", results: [vancouverBc, vancouverWa] });
    const onPreview = vi.fn();
    const onSelect = vi.fn();
    renderSearch({ onPreview, onSelect });

    await user.type(screen.getByRole("searchbox"), "vancouver");
    const bc = await screen.findByRole("button", { name: /British Columbia/ });
    expect(bc).toHaveTextContent("49.26, -123.11");

    await user.hover(bc);
    expect(onPreview).toHaveBeenCalledWith(vancouverBc);
    await user.unhover(bc);
    expect(onPreview).toHaveBeenLastCalledWith(null);

    bc.focus();
    expect(onPreview).toHaveBeenCalledWith(vancouverBc);
    await user.click(bc);
    expect(onSelect).toHaveBeenCalledWith(vancouverBc);
    expect(onPreview).toHaveBeenLastCalledWith(null);
  });

  it("clears a hovered preview when a new result set arrives", async () => {
    const user = userEvent.setup();
    const onPreview = vi.fn();
    vi.spyOn(api, "search")
      .mockResolvedValueOnce({ query: "vancouver", results: [vancouverBc] })
      .mockResolvedValueOnce({ query: "banff", results: [banff] });
    renderSearch({ onPreview });

    await user.type(screen.getByRole("searchbox"), "vancouver");
    const bc = await screen.findByRole("button", { name: /British Columbia/ }, { timeout: 1_000 });
    await user.hover(bc);
    expect(onPreview).toHaveBeenCalledWith(vancouverBc);

    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "banff");
    expect(await screen.findByText("Banff National Park", {}, { timeout: 1_000 })).toBeInTheDocument();
    expect(onPreview).toHaveBeenLastCalledWith(null);
  });

  it("identifies replacement mode and disables its input while persistence is pending", () => {
    renderSearch({ editingName: "Old Camp", disabled: true });

    expect(screen.getByRole("heading", { name: "Move Old Camp" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toBeDisabled();
  });
});
