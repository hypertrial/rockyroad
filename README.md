# RockyRoad

Self-hosted, local-first Canada + USA road-trip planner. After geographic data is built, the app runs with no mapping, routing, geocoding, database, or cloud APIs.

RockyRoad is a monorepo:

- `apps/web` — React 19, Vite, MapLibre, TanStack Query/Router, Zustand
- `services/api` — FastAPI, DuckDB (`spatial`, `fts`), Valhalla client, data CLI
- `data/` — generated artifacts (not committed)
- `compose.yaml` — Caddy + API + Valhalla on an internal Docker network

## Quick start

```bash
./scripts/dev
```

The script installs missing Python/frontend dependencies, copies `.env.example` if needed, then starts the API and Vite app together. Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/maps` to FastAPI; PMTiles come from `data/maps`. Routing still needs Valhalla on `:8002` (`docker compose up -d valhalla` after `build-routing`; `docker-compose` works if the plugin is missing). `build-routing` uses host Valhalla tools when they are on PATH, otherwise Docker. If the repo path contains a space, set `ROCKYROAD_VALHALLA_FILES` to the Docker-visible tile directory printed by `build-routing` (typically `~/.cache/rockyroad/valhalla`).

Build the sample Prince Edward Island extract first if you want a real map and local search (needs Java 21+, a local `tools/planetiler.jar`, and Osmium or Docker for `build-places`; multi-region `update-osm` still needs host Osmium to merge):

```bash
uv run rockyroad-data update-osm --profile sample
uv run rockyroad-data build-map
uv run rockyroad-data build-routing
uv run rockyroad-data build-places
```

Or serve the assembled stack:

```bash
pnpm build
docker compose up --build
```

Open `http://127.0.0.1:8080` with Compose.

## Commands

```bash
uv run rockyroad-data update-osm
uv run rockyroad-data build-map
uv run rockyroad-data build-routing
uv run rockyroad-data build-places
uv run rockyroad-data status
```

`update-osm` is the only command allowed to use the network. It downloads allow-listed Geofabrik extracts from `config/regions.yaml`. Everything else is offline.

Full Canada + USA:

```bash
uv run rockyroad-data update-osm --profile canada-usa
```

See [docs/data-build.md](docs/data-build.md) for disk/RAM expectations, replacement, rollback, and attribution.

## Runtime rules

- One FastAPI process owns DuckDB writes (`uvicorn --workers 1`).
- The data CLI never writes `data/rockyroad.duckdb`.
- Canonical trip state is waypoint coordinates plus routing settings. Cached geometry is disposable.
- MapLibre loads only `/maps/north-america.pmtiles` and `/map/style.json`. There is no Mapbox, Google, or OpenFreeMap fallback.

## Tests

```bash
uv run ruff check services/api
uv run ruff format --check services/api
uv run pyright
uv run pytest
pnpm typecheck
pnpm lint
pnpm test
pnpm build
make compose-config
```

## License

Application code is MIT. OpenStreetMap data is © OpenStreetMap contributors and licensed under ODbL.
