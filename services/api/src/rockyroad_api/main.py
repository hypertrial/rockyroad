from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rockyroad_api.db import Database
from rockyroad_api.geo import import_geo_if_changed
from rockyroad_api.routers import health, search, trips
from rockyroad_api.routing import ValhallaClient
from rockyroad_api.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(config)
        app.state.db = db
        app.state.valhalla = ValhallaClient(config)
        import_geo_if_changed(db)
        try:
            yield
        finally:
            db.close()

    app = FastAPI(title="RockyRoad", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8080"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(trips.router, prefix="/api")
    maps_dir = config.maps_dir
    maps_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/maps", StaticFiles(directory=str(maps_dir)), name="maps")
    return app


app = create_app()
