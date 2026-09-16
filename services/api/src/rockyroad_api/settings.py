from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ROCKYROAD_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    duckdb_path: Path = Path("data/rockyroad.duckdb")
    geo_dir: Path = Path("data/geo")
    maps_dir: Path = Path("data/maps")
    osm_dir: Path = Path("data/osm")
    routing_dir: Path = Path("data/routing/valhalla")
    region_profile: str = "sample"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    valhalla_url: str = Field(
        default="http://127.0.0.1:8002",
        validation_alias=AliasChoices("valhalla_url", "VALHALLA_URL", "ROCKYROAD_VALHALLA_URL"),
    )
    valhalla_timeout_s: float = Field(
        default=30.0,
        validation_alias=AliasChoices("valhalla_timeout_s", "VALHALLA_TIMEOUT_S", "ROCKYROAD_VALHALLA_TIMEOUT_S"),
    )
    recent_search_limit: int = 25
    max_search_results: int = 20
    extensions_dir: Path | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
