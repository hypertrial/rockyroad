# RockyRoad

Canada + USA road-trip planner. The default mode uses hosted OpenFreeMap tiles, OpenRouteService routing, and Photon search so you can plan across the continent without building a 60–100 GB local extract. An explicit `local` mode still runs the PEI offline stack from downloaded OSM artifacts.

RockyRoad is a monorepo:

- `apps/web` — React 19, Vite, MapLibre, TanStack Query/Router, dnd-kit, and Playwright
- `services/api` — FastAPI, DuckDB, OpenRouteService/Photon or Valhalla clients, data CLI
- `data/` — generated local artifacts (not committed)
- `compose.yaml` — Caddy + API; Valhalla starts only with `--profile local`

## Quick start

1. Copy `.env.example` to `.env` if needed.
2. Put a free OpenRouteService key in `ROCKYROAD_ORS_API_KEY` ([openrouteservice.org](https://openrouteservice.org/)).
3. Start the app:

```bash
./scripts/dev
```

The script installs missing Python/frontend dependencies, copies `.env.example` if needed, then starts the API, waits until `/api/health` responds, and only then starts Vite. It exits if another RockyRoad API is already on `:8000`. Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/maps` to FastAPI.

Hosted mode is personal/self-hosted use: OpenFreeMap, OpenRouteService, and Photon have no SLA. OpenRouteService’s free plan is about 2,000 directions and 500 optimizations per day. Photon is a best-effort demo and needs an identifying User-Agent. The API keeps the ORS key server-side; the browser only loads OpenFreeMap tiles.

Or serve the assembled hosted stack:

```bash
pnpm build
docker compose up --build
```

Open `http://127.0.0.1:8080` with Compose.

## Local / offline PEI mode

Set `ROCKYROAD_PROVIDER_MODE=local` in `.env` before startup. There is no automatic failover. Local mode uses PMTiles, Valhalla, and DuckDB places, and stays inside the downloaded extract (the default `sample` extract is Prince Edward Island).

```bash
uv run rockyroad-data update-osm --profile sample
uv run rockyroad-data build-map
uv run rockyroad-data build-routing
uv run rockyroad-data build-places
docker compose --profile local up -d valhalla
ROCKYROAD_PROVIDER_MODE=local ./scripts/dev
```

If the repo path contains a space, set `ROCKYROAD_VALHALLA_FILES` to the Docker-visible tile directory printed by `build-routing` (typically `~/.cache/rockyroad/valhalla`).

A full local `canada-usa` extract is optional and large. Hosted mode is the supported way to cover Canada and the USA without that build.

## Commands

```bash
uv run rockyroad-data update-osm
uv run rockyroad-data build-map
uv run rockyroad-data build-routing
uv run rockyroad-data build-places
uv run rockyroad-data status
```

`update-osm` downloads allow-listed Geofabrik extracts from `config/regions.yaml`. Use these only for local mode.

See [docs/data-build.md](docs/data-build.md) for hosted limits, local disk/RAM expectations, replacement, rollback, and attribution.

## Runtime rules

- One FastAPI process owns DuckDB writes (`uvicorn --workers 1`).
- The data CLI never writes `data/rockyroad.duckdb`.
- Canonical trip state is waypoint coordinates plus routing settings. Cached geometry is disposable.
- Hosted mode: MapLibre loads OpenFreeMap Liberty; search and routing go through FastAPI to Photon and OpenRouteService.
- Local mode: MapLibre loads only `/maps/north-america.pmtiles` and `/map/style.json`.

## Tests

Development feedback: `scripts/verify-fast`. Completion: `scripts/verify`.

```bash
uv run ruff check services/api
uv run ruff format --check services/api
uv run pyright
uv run pytest
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm test:e2e
make compose-config
```

Install the Playwright Chromium runtime once with
`pnpm --filter @rockyroad/web exec playwright install chromium`. The E2E suite
uses mocked API responses and a local empty map style, so it does not call live
tile, search, or routing providers.

`make compose-config` still accepts either `docker-compose` or `docker compose` if the Compose plugin is missing locally.

## License

Application code is MIT. OpenStreetMap data is © OpenStreetMap contributors and licensed under ODbL.
