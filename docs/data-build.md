# RockyRoad data builds

RockyRoad never talks to hosted map or geocoder APIs at runtime. Geographic artifacts are built once, stored under `data/`, and served locally.

```text
OSM PBF
├─→ Planetiler → data/maps/north-america.pmtiles
├─→ Valhalla → data/routing/valhalla/
└─→ Osmium + Polars → data/geo/*.parquet → DuckDB (API-owned)
```

## Profiles

`config/regions.yaml` is an allow-list. `update-osm` refuses any extract that is not listed.

| Profile | Extracts | Use |
| --- | --- | --- |
| `sample` (default) | Prince Edward Island | Local development and CI-sized vertical slice |
| `canada-usa` | `north-america/canada`, `north-america/us` | Full coverage |

```bash
uv run rockyroad-data update-osm --profile sample
uv run rockyroad-data build-map
uv run rockyroad-data build-routing
uv run rockyroad-data build-places
```

## Expected size and time

These are order-of-magnitude numbers; hardware and Geofabrik freshness change them.

| Profile | Download | PMTiles | Valhalla tiles | Parquet | RAM | Wall time |
| --- | --- | --- | --- | --- | --- | --- |
| sample (PEI) | ~30–50 MB | ~40–80 MB | ~100–250 MB | <20 MB | 4 GB | 10–30 min |
| canada-usa | ~10–15 GB | 20–40 GB | 40–80 GB | 1–3 GB | 32–64 GB | many hours |

Keep generated PBF, PMTiles, graphs, Parquet, and DuckDB files out of Git.

## Host tools

- `osmium` for merge, tag filter, and GeoJSONSeq export
- Java 21+ for Planetiler (`tools/planetiler.jar` is downloaded by `build-map`)
- `valhalla_build_tiles` and `valhalla_build_extract` for the routing graph

Planetiler is also available as `infra/map/Dockerfile` if you prefer a containerized map build.

## Incremental replacement

Each command writes a versioned `manifest.json` next to its artifacts and replaces files atomically (`*.tmp` then rename).

The API imports Parquet on startup and through `POST /api/admin/import-geo`. Import swaps into a staging table, rebuilds the FTS index, then replaces `geo_features`. If the new manifest is incomplete, the previous searchable dataset stays in place.

To roll back a build, restore the previous `data/geo`, `data/maps`, or `data/routing/valhalla` directory and restart the API. Route geometry cache keys include the Valhalla data version, so old legs are recomputed automatically.

## Backup and restore

Copy these paths:

```text
data/rockyroad.duckdb
data/geo/
data/maps/north-america.pmtiles
data/routing/valhalla/
data/osm/manifest.json
```

Restore by replacing the same paths and restarting Compose. Trip tables live only in DuckDB; geographic datasets are immutable Parquet.

## Local development

```bash
./scripts/dev
```

That starts FastAPI on `:8000` and Vite on `:5173`. Vite proxies `/api` and `/maps` to the API, which serves `data/maps` with byte ranges. Routing still needs a local Valhalla process on `:8002` after `build-routing`.

## Offline verification

After artifacts exist:

1. Local: `./scripts/dev` and open `http://127.0.0.1:5173`
2. Assembled: `pnpm build && docker compose up --build`
3. Confirm `GET http://127.0.0.1:8000/api/health` or `http://127.0.0.1:8080/api/health` reports local DuckDB, geo, maps, and routing.
4. Recreate the assembled stack with no public egress (`internal: true` on the Compose network, no extra ports except 8080).
5. Create a trip, search a local place, add two stops, build a route, restart the API, and confirm the trip is still present.

The runtime containers must not contain Mapbox, Google Maps, OpenFreeMap, or other hosted tile URLs. `apps/web/public/map/style.json` points only at `pmtiles:///maps/north-america.pmtiles`.

## Attribution and ODbL

- © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright)
- Geofabrik distributes the regional extracts used by `update-osm`
- Planetiler / OpenMapTiles schema for the vector basemap
- Valhalla for routing

If you publish a map produced from this pipeline, keep OSM attribution visible. Produced tiles, graphs, and Parquet inherit ODbL share-alike obligations.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `update-osm` rejects an extract | Path is not allow-listed | Add it under `config/regions.yaml` |
| Blank map | Missing PMTiles | `build-map`, then confirm `/maps/north-america.pmtiles` |
| Route 503 | Valhalla graph missing or service down | `build-routing` and check `data/routing/valhalla/manifest.json` |
| Empty search | Parquet not imported | `build-places`, then restart API or `POST /api/admin/import-geo` |
| DuckDB extension download | Image was built without `INSTALL spatial/fts` | Rebuild `infra/api/Dockerfile` |
