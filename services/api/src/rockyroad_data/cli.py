from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from rockyroad_data.manifests import artifact_ready
from rockyroad_data.maps import build_map
from rockyroad_data.osm import update_osm
from rockyroad_data.paths import (
    GEO_MANIFEST,
    MAP_MANIFEST,
    MERGED_PBF,
    OSM_MANIFEST,
    PARQUET_DATASETS,
    PMTILES_PATH,
    ROUTING_MANIFEST,
)
from rockyroad_data.places import build_places
from rockyroad_data.routing import build_routing

app = typer.Typer(no_args_is_help=True, help="Build offline RockyRoad geographic artifacts.")


@app.command("update-osm")
def update_osm_command(
    profile: Annotated[str | None, typer.Option(help="Region profile from config/regions.yaml")] = None,
    regions: Annotated[Path | None, typer.Option(help="Optional alternate regions.yaml")] = None,
) -> None:
    """Download allow-listed Geofabrik extracts and merge them locally."""
    manifest = update_osm(profile, regions)
    typer.echo(f"OSM profile {manifest['profile']} version {manifest['version']}")


@app.command("build-map")
def build_map_command() -> None:
    """Generate a local OpenMapTiles PMTiles basemap from the merged OSM extract.

    Requires a local tools/planetiler.jar. This command does not use the network.
    """
    manifest = build_map()
    typer.echo(f"Wrote PMTiles version {manifest['version']}")


@app.command("build-routing")
def build_routing_command() -> None:
    """Build a local Valhalla graph from the merged OSM extract."""
    manifest = build_routing()
    typer.echo(f"Wrote Valhalla graph version {manifest['version']}")
    docker_files = manifest.get("docker_files")
    if docker_files and Path(str(docker_files)).resolve() != ROUTING_MANIFEST.parent.resolve():
        typer.echo(f"Set ROCKYROAD_VALHALLA_FILES={docker_files} before starting Valhalla.")


@app.command("build-places")
def build_places_command() -> None:
    """Extract searchable places into typed Parquet datasets."""
    manifest = build_places()
    typer.echo(f"Wrote places version {manifest['version']}")


@app.command("status")
def status_command() -> None:
    """Show which local artifacts exist."""
    artifacts = {
        "osm": OSM_MANIFEST.is_file() and artifact_ready(MERGED_PBF),
        "map": MAP_MANIFEST.is_file() and artifact_ready(PMTILES_PATH),
        "routing": ROUTING_MANIFEST.is_file()
        and (
            artifact_ready(ROUTING_MANIFEST.parent / "valhalla_tiles.tar")
            or artifact_ready(ROUTING_MANIFEST.parent / "valhalla_tiles")
        ),
        "geo": GEO_MANIFEST.is_file()
        and all(artifact_ready(GEO_MANIFEST.parent / f"{name}.parquet") for name in PARQUET_DATASETS),
    }
    for label, ready in artifacts.items():
        typer.echo(f"{label}: {'ready' if ready else 'missing'}")


if __name__ == "__main__":
    app()
