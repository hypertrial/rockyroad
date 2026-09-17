from __future__ import annotations

from typing import Protocol

from rockyroad_api.models import SearchResponse, StopOut, TripSettingsOut, Viewport
from rockyroad_api.routing import RouteComputation


class RouteProvider(Protocol):
    def request_route(self, stops: list[StopOut], settings: TripSettingsOut) -> RouteComputation: ...


class PlaceSearch(Protocol):
    def search(self, query: str, viewport: Viewport | None = None) -> SearchResponse: ...


def redact_secret(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text
