import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { HealthResponse } from "../lib/types";
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

function renderSearch(health: HealthResponse = hosted) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SearchBox onSelect={vi.fn()} health={health} />
    </QueryClientProvider>,
  );
}

describe("SearchBox", () => {
  it("debounces hosted search and keeps previous results visible", async () => {
    const user = userEvent.setup();
    let resolveSearch: ((value: { query: string; results: [] }) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveSearch = (value) =>
              resolve({
                ok: true,
                status: 200,
                json: async () => value,
              });
          }),
      ),
    );
    renderSearch();
    await user.type(screen.getByRole("searchbox"), "ca");
    expect(globalThis.fetch).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1), { timeout: 1000 });
    resolveSearch?.({ query: "ca", results: [] });
    expect(await screen.findByText("No matching places.")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
