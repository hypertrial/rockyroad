from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from rockyroad_data.maps import build_map
from rockyroad_data.osm import update_osm
from rockyroad_data.paths import GEO_MANIFEST, MAP_MANIFEST, OSM_MANIFEST, ROUTING_MANIFEST
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
    """Generate a local OpenMapTiles PMTiles basemap from the merged OSM extract."""
    manifest = build_map()
    typer.echo(f"Wrote PMTiles version {manifest['version']}")


@app.command("build-routing")
def build_routing_command() -> None:
    """Build a local Valhalla graph from the merged OSM extract."""
    manifest = build_routing()
    typer.echo(f"Wrote Valhalla graph version {manifest['version']}")


@app.command("build-places")
def build_places_command() -> None:
    """Extract searchable places into typed Parquet datasets."""
    manifest = build_places()
    typer.echo(f"Wrote places version {manifest['version']}")


@app.command("status")
def status_command() -> None:
    """Show which local artifacts exist."""
    for label, path in (
        ("osm", OSM_MANIFEST),
        ("map", MAP_MANIFEST),
        ("routing", ROUTING_MANIFEST),
        ("geo", GEO_MANIFEST),
    ):
        typer.echo(f"{label}: {'ready' if path.exists() else 'missing'} ({path})")


if __name__ == "__main__":
    app()
