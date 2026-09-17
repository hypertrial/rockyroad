from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderMode = Literal["hosted", "local"]


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
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    provider_mode: ProviderMode = "hosted"
    valhalla_url: str = Field(
        default="http://127.0.0.1:8002",
        validation_alias=AliasChoices("valhalla_url", "VALHALLA_URL", "ROCKYROAD_VALHALLA_URL"),
    )
    valhalla_timeout_s: float = Field(
        default=30.0,
        validation_alias=AliasChoices("valhalla_timeout_s", "VALHALLA_TIMEOUT_S", "ROCKYROAD_VALHALLA_TIMEOUT_S"),
    )
    ors_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ors_api_key", "ORS_API_KEY", "ROCKYROAD_ORS_API_KEY"),
    )
    ors_base_url: str = "https://api.heigit.org/openrouteservice"
    ors_optimization_url: str = "https://api.heigit.org/vroom/v0/optimization"
    ors_timeout_s: float = 30.0
    hosted_routing_version: str = "ors-v1"
    photon_url: str = "https://photon.komoot.io"
    photon_user_agent: str = (
        "RockyRoad/0.1 (personal Canada+USA road-trip planner; https://github.com/hypertrial/rockyroad)"
    )
    photon_timeout_s: float = 8.0
    photon_cache_ttl_s: int = 3600
    photon_cache_limit: int = 500
    openfreemap_style_url: str = "https://tiles.openfreemap.org/styles/liberty"
    recent_search_limit: int = 25
    max_search_results: int = 20
    extensions_dir: Path | None = None

    @property
    def hosted(self) -> bool:
        return self.provider_mode == "hosted"

    def ors_key_value(self) -> str:
        return self.ors_api_key.get_secret_value().strip()

    def has_ors_key(self) -> bool:
        return bool(self.ors_key_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
