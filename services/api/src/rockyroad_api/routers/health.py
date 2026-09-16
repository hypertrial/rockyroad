from __future__ import annotations

from fastapi import APIRouter, Request

from rockyroad_api.geo import current_geo_version, import_geo_if_changed
from rockyroad_api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    db = request.app.state.db
    settings = db.settings
    maps_ok = (settings.maps_dir / "north-america.pmtiles").exists()
    routing_ok = (settings.routing_dir / "manifest.json").exists() or (
        settings.routing_dir / "valhalla_tiles.tar"
    ).exists()
    geo_ok = current_geo_version(db) is not None or (settings.geo_dir / "manifest.json").exists()
    status = "ok" if geo_ok and maps_ok and routing_ok else "degraded"
    detail = None
    if not maps_ok:
        detail = (
            "PMTiles basemap is missing. "
            "Run uv run rockyroad-data update-osm --profile sample && uv run rockyroad-data build-map."
        )
    elif not routing_ok:
        detail = "Valhalla graph is missing. Run rockyroad-data build-routing."
    elif not geo_ok:
        detail = "Place datasets are missing. Run rockyroad-data build-places."
    return HealthResponse(
        status=status,
        duckdb=True,
        geo=geo_ok,
        routing=routing_ok,
        maps=maps_ok,
        data_version=current_geo_version(db),
        detail=detail,
    )


@router.post("/admin/import-geo")
def import_geo(request: Request) -> dict[str, object]:
    return import_geo_if_changed(request.app.state.db)


@router.get("/ready")
def ready(request: Request) -> dict[str, bool]:
    return {"ready": True, "duckdb": request.app.state.db.conn is not None}
