# RockyRoad project notes

RockyRoad is a Canada + USA road-trip planner monorepo. Default hosted
mode uses OpenFreeMap tiles, OpenRouteService routing, and Photon search.
An explicit `local` mode still runs the PEI offline stack from downloaded OSM
artifacts.

Use the `rockyroad-engineering` workspace from `.pad.toml`. Follow `AGENTS.md`
and the local `pad-engineering` skill. Keep ticket bodies, exports, credentials,
and local Pad state out of git.

## Invariants

- Hosted and `local` provider modes do not fail over. Set
  `ROCKYROAD_PROVIDER_MODE` before startup.
- The OpenRouteService key stays in `ROCKYROAD_ORS_API_KEY` on the API. The
  browser never receives it.
- One FastAPI process owns DuckDB writes (`uvicorn --workers 1`). The data CLI
  never writes `data/rockyroad.duckdb`.
- Canonical trip state is waypoint coordinates plus routing settings. Cached
  geometry is disposable.
- Generated geographic artifacts stay under gitignored `data/`.
- Hosted mode: MapLibre loads OpenFreeMap Liberty; search and routing go through
  FastAPI to Photon and OpenRouteService.
- Local mode: MapLibre loads only `/maps/north-america.pmtiles` and
  `/map/style.json`.

## Verification

- Fast: `uv run ruff check services/api`, `uv run pytest`, `pnpm typecheck`,
  `pnpm lint`, and `pnpm test`.
- Completion: also `uv run ruff format --check services/api`, `uv run pyright`,
  `pnpm build`, `pnpm test:e2e`, and `make compose-config`.

These commands are wrapped by `scripts/verify-fast` and `scripts/verify`.
GitHub Actions remains the independent verification source of truth.
