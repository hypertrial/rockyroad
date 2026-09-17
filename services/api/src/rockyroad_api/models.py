from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

NA_LAT_MIN = 15.0
NA_LAT_MAX = 85.0
NA_LON_MIN = -180.0
NA_LON_MAX = -50.0


def validate_na_coordinate(lon: float, lat: float) -> None:
    if not (NA_LON_MIN <= lon <= NA_LON_MAX and NA_LAT_MIN <= lat <= NA_LAT_MAX):
        raise ValueError("coordinates must fall within Canada and the USA")


class Viewport(BaseModel):
    west: float
    south: float
    east: float
    north: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2.0, (self.south + self.north) / 2.0)


class PlaceResult(BaseModel):
    id: str
    name: str
    feature_type: str
    dataset: str
    lon: float
    lat: float
    score: float
    population: int | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[PlaceResult]


class StopIn(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    lon: float
    lat: float
    place_id: str | None = None

    @field_validator("lon", "lat")
    @classmethod
    def _finite(cls, value: float) -> float:
        if value != value:  # NaN
            raise ValueError("coordinate must be finite")
        return value

    def validate_location(self) -> StopIn:
        validate_na_coordinate(self.lon, self.lat)
        return self


class StopOut(BaseModel):
    id: UUID
    trip_id: UUID
    position: int
    name: str
    lon: float
    lat: float
    place_id: str | None
    created_at: datetime


class TripSettingsIn(BaseModel):
    avoid_tolls: bool = False
    avoid_highways: bool = False
    avoid_ferries: bool = False
    costing: Literal["auto"] = "auto"
    optimize: bool = False
    selected_alternative: int = 0


class TripSettingsOut(TripSettingsIn):
    trip_id: UUID
    updated_at: datetime


class TripCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    stops: list[StopIn] = Field(default_factory=list)
    settings: TripSettingsIn = Field(default_factory=TripSettingsIn)


class TripUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    settings: TripSettingsIn | None = None


class Maneuver(BaseModel):
    instruction: str
    type: int | None = None
    distance_m: float
    duration_s: float
    begin_shape_index: int = 0


class RouteAlternative(BaseModel):
    index: int
    distance_m: float
    duration_s: float
    geometry: dict[str, Any]
    maneuvers: list[Maneuver]


class RouteResponse(BaseModel):
    trip_id: UUID
    cache_hit: bool
    data_version: str
    alternatives: list[RouteAlternative]


class TripOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    stops: list[StopOut]
    settings: TripSettingsOut
    route: RouteResponse | None = None


class TripSummary(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    stop_count: int


class SavedPlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lon: float
    lat: float
    place_id: str | None = None
    notes: str | None = None

    def validate_location(self) -> SavedPlaceIn:
        validate_na_coordinate(self.lon, self.lat)
        return self


class SavedPlaceOut(BaseModel):
    id: UUID
    name: str
    lon: float
    lat: float
    place_id: str | None
    notes: str | None
    created_at: datetime


class RecentSearchOut(BaseModel):
    id: UUID
    query: str
    result_place_id: str | None
    created_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    duckdb: bool
    geo: bool
    routing: bool
    maps: bool
    data_version: str | None = None
    detail: str | None = None
    bounds: list[float] | None = None
    profile: str | None = None
    provider_mode: Literal["hosted", "local"] = "local"
    map_style_url: str | None = None
    map_provider: str | None = None
    routing_provider: str | None = None
    search_provider: str | None = None
