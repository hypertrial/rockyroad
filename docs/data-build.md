# RockyRoad data and hosted providers

The default `ROCKYROAD_PROVIDER_MODE=hosted` planner does not require a Canada+USA OSM extract. The browser loads OpenFreeMap Liberty tiles. FastAPI proxies search to Photon and routing/optimization to OpenRouteService. Large local `canada-usa` artifacts are optional.

`local` mode is selected explicitly before startup. It never talks to hosted map or geocoder APIs at runtime. Geographic artifacts are built once, stored under `data/`, and served locally.

```text
hosted:
  Browser → OpenFreeMap tiles
  FastAPI → Photon search
  FastAPI → OpenRouteService directions + VROOM optimization

local:
  OSM PBF
  ├─→ Planetiler → data/maps/north-america.pmtiles
  ├─→ Valhalla → data/routing/valhalla/
  └─→ Osmium + Polars → data/geo/*.parquet → DuckDB (API-owned)
```

## Hosted providers

Set `ROCKYROAD_ORS_API_KEY` from [openrouteservice.org](https://openrouteservice.org/). Optional overrides:

| Variable | Default |
| --- | --- |
| `ROCKYROAD_ORS_BASE_URL` | `https://api.heigit.org/openrouteservice` |
| `ROCKYROAD_ORS_OPTIMIZATION_URL` | `https://api.heigit.org/vroom/v0/optimization` |
| `ROCKYROAD_PHOTON_URL` | `https://photon.komoot.io` |
| `ROCKYROAD_PHOTON_USER_AGENT` | identifying RockyRoad User-Agent |
| `ROCKYROAD_OPENFREEMAP_STYLE_URL` | `https://tiles.openfreemap.org/styles/liberty` |

These services have no SLA. Personal use only.

- OpenRouteService free plan: about 2,000 directions/day, 500 optimizations/day, 50 waypoints, 6,000 km driving routes. Alternative routes are limited to 100 km, so RockyRoad returns one hosted route. VROOM stop ordering uses the standard driving profile; the follow-up directions request applies RockyRoad avoid-toll/highway/ferry options.
- Photon public demo: reasonable-use, no guarantee. RockyRoad identifies itself with a User-Agent, caches results, and biases toward the current map center without clipping the query to the viewport.
- OpenFreeMap: donation-funded public tiles, no API key.

The OpenRouteService key never leaves the API process. It is not included in `/api/health`, frontend assets, or error text.

Switching to `local` requires a restart (`ROCKYROAD_PROVIDER_MODE=local`). There is no automatic failover.

## Local profiles

`config/regions.yaml` is an allow-list. `update-osm` refuses any extract that is not listed.

| Profile | Extracts | Use |
| --- | --- | --- |
| `sample` (default) | Prince Edward Island | Local development and CI-sized vertical slice |
| `canada-usa` | `north-america/canada`, `north-america/us` | Full local coverage; hosted mode is the recommended alternative |

```bash
uv run rockyroad-data update-osm --profile sample
uv run rockyroad-data build-map
uv run rockyroad-data build-routing
uv run rockyroad-data build-places
```

## Expected size and time

These are order-of-magnitude numbers; hardware and Geofabrik freshness change them. Hosted mode does not need these builds.

| Profile | Download | PMTiles | Valhalla tiles | Parquet | RAM | Wall time |
| --- | --- | --- | --- | --- | --- | --- |
| sample (PEI) | ~30–50 MB | ~40–80 MB | ~100–250 MB | <20 MB | 4 GB | 10–30 min |
| canada-usa | ~10–15 GB | 20–40 GB | 40–80 GB | 1–3 GB | 32–64 GB | many hours |

Keep generated PBF, PMTiles, graphs, Parquet, and DuckDB files out of Git.

## Host tools

- `osmium` for multi-region merge. `build-places` uses host `osmium` when present and otherwise Docker (`iboates/osmium:1.19.0`). Sample `update-osm` still copies a single extract without osmium.
- Java 21+ for Planetiler (`/usr/bin/java` on macOS is often 17; Homebrew `openjdk@21` is used if present). Place `planetiler.jar` (v0.9.0) in `tools/`. The first map build also needs Natural Earth, water polygons, and lake centerlines under `data/sources/` (copy them there, or run Planetiler once with `--download`). `build-map` itself does not fetch those files. Heap defaults to 4g; set `ROCKYROAD_PLANETILER_XMX=32g` (or similar) for `canada-usa`.
- Valhalla tools (`valhalla_build_tiles` and `valhalla_build_extract`) or Docker. `build-routing` uses the host binaries when present and otherwise builds with `ghcr.io/valhalla/valhalla-scripted`.

Planetiler is also available as `infra/map/Dockerfile` if you prefer a containerized map build. That image defaults to `-Xmx4g` via `JAVA_TOOL_OPTIONS`; override the env var for a larger extract.

## Incremental replacement

Each command writes a versioned `manifest.json` next to its artifacts and replaces files atomically (`*.tmp` then rename).

The API imports Parquet on local-mode startup and through `POST /api/admin/import-geo`. Import swaps into a staging table, rebuilds the FTS index, then replaces `geo_features`. If the new manifest is incomplete, the previous searchable dataset stays in place.

To roll back a local build, restore the previous `data/geo`, `data/maps`, or `data/routing/valhalla` directory and restart the API. Route geometry cache keys include the routing data version (`ors-v1` when hosted, the Valhalla manifest when local), so old legs are recomputed automatically.

## Backup and restore

Copy these paths:

```text
data/rockyroad.duckdb (direct development) or the Compose rockyroad-state volume
data/geo/
data/maps/north-america.pmtiles
data/routing/valhalla/
data/osm/manifest.json
```

Restore by replacing the same paths and restarting the API. Compose stores DuckDB in its `rockyroad-state` named volume while mounting generated geographic artifacts read-only from `data/`; direct development uses `data/rockyroad.duckdb`. Trip tables live only in DuckDB; geographic datasets are immutable Parquet.

On the first Compose start after upgrading from the former bind-mounted database layout, the API copies `data/rockyroad.duckdb` (and its WAL, when present) into the empty `rockyroad-state` volume. It never overwrites a database already present in the named volume. Keep the legacy file until the upgraded stack has started successfully and your trips are visible.

## Local development

```bash
./scripts/dev
```

That starts FastAPI on `:8000`, waits until `/api/health` responds, then starts Vite on `:5173`. It exits if another RockyRoad API is already answering `/api/ready` on `:8000`. Vite proxies `/api` and `/maps` to the API.

Hosted `/api/health` reports `provider_mode`, OpenFreeMap `map_style_url`, Canada+USA `bounds`, and whether `ROCKYROAD_ORS_API_KEY` is present. It does not probe third parties on every request.

Local mode still serves `data/maps` with byte ranges and frames a sample PEI map from extract `bounds`. Map clicks, pin moves, and **Build route** stay inside those bounds. Routing needs a graph plus Valhalla on `:8002`; `uv run rockyroad-data build-routing && docker compose --profile local up -d valhalla` builds the graph and publishes the service. If the repo path contains a space, Docker Desktop cannot bind-mount `data/routing/valhalla`; `build-routing` stages tiles under `~/.cache/rockyroad/valhalla` and Compose should set `ROCKYROAD_VALHALLA_FILES` to that directory.

## Offline verification

After local artifacts exist:

1. `ROCKYROAD_PROVIDER_MODE=local ./scripts/dev` and open `http://127.0.0.1:5173`
2. Assembled: `pnpm build && docker compose --profile local up --build`
3. Confirm `GET /api/health` reports local DuckDB, geo, maps, and routing.
4. Create a trip, search a local place, add two PEI stops, build a route, restart the API, and confirm the trip is still present.

## Attribution and ODbL

- © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright)
- OpenFreeMap for hosted vector tiles
- OpenRouteService / HeiGIT and VROOM for hosted routing and stop order
- Photon / Komoot for hosted search
- Geofabrik distributes the regional extracts used by `update-osm`
- Planetiler / OpenMapTiles schema for the local vector basemap
- Valhalla for local routing

Keep OSM attribution visible. Produced tiles, graphs, and Parquet inherit ODbL share-alike obligations.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Hosted health is degraded | Missing `ROCKYROAD_ORS_API_KEY` | Add a key to `.env` and restart |
| Hosted route 429 | OpenRouteService quota or rate limit | Wait for the rolling window; reuse cached routes |
| Hosted route 422 / stops cannot connect | One or more stops are not near a routable road | Move each stop onto a nearby road and retry |
| Hosted route 502/503 | OpenRouteService rejected the request or is unavailable | Retry, then check the provider configuration and service status |
| Hosted search 429/503 | Photon throttle or outage | Wait and retry; results are cached after the first success |
| `update-osm` rejects an extract | Path is not allow-listed | Add it under `config/regions.yaml` |
| Blank local map | Missing PMTiles | `build-map`, then confirm `/maps/north-america.pmtiles` |
| Local route 503 | Valhalla graph missing or service down | `build-routing`, then `docker compose --profile local up -d valhalla`. If the repo path has a space, set `ROCKYROAD_VALHALLA_FILES` |
| Local route 422 / no roads near stops | Pins are outside the downloaded extract (`sample` is PEI-only) | Drop stops inside `/api/health` `bounds`, switch to hosted mode, or rebuild with `update-osm --profile canada-usa` |
| Empty local search | Parquet not imported | `uv run rockyroad-data build-places` (host osmium or Docker), then restart the API or `POST /api/admin/import-geo` |
| DuckDB extension download | Image was built without `INSTALL spatial/fts` | Rebuild `infra/api/Dockerfile` |
