from __future__ import annotations

from functools import lru_cache

from rockyroad_api.db import Database
from rockyroad_api.routing import ValhallaClient
from rockyroad_api.settings import Settings, get_settings


@lru_cache
def get_database() -> Database:
    return Database(get_settings())


@lru_cache
def get_router_client() -> ValhallaClient:
    return ValhallaClient(get_settings())


def reset_singletons() -> None:
    get_database.cache_clear()
    get_router_client.cache_clear()
    get_settings.cache_clear()


def settings() -> Settings:
    return get_settings()
