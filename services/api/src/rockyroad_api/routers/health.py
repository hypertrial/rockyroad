from __future__ import annotations

from fastapi import APIRouter, Request

from rockyroad_api.geo import (
    HOSTED_PROFILE,
    current_geo_version,
    extract_bounds,
    extract_profile,
    fts_index_exists,
    hosted_bounds,
    import_geo_if_changed,
)
from rockyroad_api.models import HealthResponse
from rockyroad_data.manifests import artifact_ready

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    db = request.app.state.db
    settings = db.settings
    if settings.hosted:
        maps_ok = bool(settings.openfreemap_style_url)
        routing_ok = settings.has_ors_key()
        geo_ok = bool(settings.photon_url)
        status = "ok" if maps_ok and routing_ok and geo_ok else "degraded"
        detail = None
        if not routing_ok:
            detail = "OpenRouteService API key is missing. Set ROCKYROAD_ORS_API_KEY to build routes."
        elif not maps_ok:
            detail = "OpenFreeMap style URL is missing. Set ROCKYROAD_OPENFREEMAP_STYLE_URL."
        elif not geo_ok:
            detail = "Photon search URL is missing. Set ROCKYROAD_PHOTON_URL."
        return HealthResponse(
            status=status,
            duckdb=True,
            geo=geo_ok,
            routing=routing_ok,
            maps=maps_ok,
            data_version=settings.hosted_routing_version,
            detail=detail,
            bounds=hosted_bounds(),
            profile=HOSTED_PROFILE,
            provider_mode="hosted",
            map_style_url=settings.openfreemap_style_url,
            map_provider="openfreemap",
            routing_provider="openrouteservice",
            search_provider="photon",
        )

    maps_ok = artifact_ready(settings.maps_dir / "north-america.pmtiles")
    routing_ok = artifact_ready(settings.routing_dir / "valhalla_tiles.tar") or artifact_ready(
        settings.routing_dir / "valhalla_tiles"
    )
    version = current_geo_version(db)
    geo_ok = version is not None
    fts_ok = db.read(fts_index_exists) if geo_ok else False
    status = "ok" if geo_ok and fts_ok and maps_ok and routing_ok else "degraded"
    detail = None
    if not maps_ok:
        detail = (
            "PMTiles basemap is missing. "
            "Run uv run rockyroad-data update-osm --profile sample && uv run rockyroad-data build-map."
        )
    elif not routing_ok:
        detail = (
            "Valhalla graph is missing. "
            "Run uv run rockyroad-data build-routing && docker compose --profile local up -d valhalla."
        )
    elif not geo_ok:
        detail = "Place datasets are missing. Run uv run rockyroad-data build-places."
    if geo_ok and not fts_ok:
        warning = (
            "Local search index is unavailable; search is using a slower fallback. "
            "Retry the place import to rebuild it."
        )
        detail = f"{detail} {warning}" if detail else warning
    bounds = extract_bounds(settings.osm_dir)
    return HealthResponse(
        status=status,
        duckdb=True,
        geo=geo_ok,
        routing=routing_ok,
        maps=maps_ok,
        data_version=version,
        detail=detail,
        bounds=bounds,
        profile=extract_profile(settings.osm_dir),
        provider_mode="local",
        map_style_url="/map/style.json" if maps_ok else None,
        map_provider="pmtiles" if maps_ok else None,
        routing_provider="valhalla",
        search_provider="duckdb",
    )


@router.post("/admin/import-geo")
def import_geo(request: Request) -> dict[str, object]:
    return import_geo_if_changed(request.app.state.db)


@router.get("/ready")
def ready(request: Request) -> dict[str, bool]:
    return {"ready": True, "duckdb": request.app.state.db.conn is not None}
