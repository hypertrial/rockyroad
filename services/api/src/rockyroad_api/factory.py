from __future__ import annotations

from rockyroad_api.db import Database
from rockyroad_api.ors import OpenRouteServiceClient
from rockyroad_api.photon import PhotonSearch
from rockyroad_api.providers import PlaceSearch, RouteProvider
from rockyroad_api.routing import ValhallaClient
from rockyroad_api.search import LocalPlaceSearch
from rockyroad_api.settings import Settings


def create_route_provider(settings: Settings) -> RouteProvider:
    if settings.hosted:
        return OpenRouteServiceClient(settings)
    return ValhallaClient(settings)


def create_place_search(settings: Settings, db: Database) -> PlaceSearch:
    if settings.hosted:
        return PhotonSearch(settings, db)
    return LocalPlaceSearch(db)
