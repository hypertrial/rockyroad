from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rockyroad_api.db import Database
from rockyroad_api.factory import create_place_search, create_route_provider
from rockyroad_api.geo import import_geo_if_changed
from rockyroad_api.routers import health, search, trips
from rockyroad_api.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(config)
        app.state.db = db
        app.state.routing = create_route_provider(config)
        app.state.search = create_place_search(config, db)
        if not config.hosted:
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
    if maps_dir.is_dir():
        app.mount("/maps", StaticFiles(directory=str(maps_dir)), name="maps")
    else:

        @app.get("/maps/{path:path}", include_in_schema=False)
        def missing_map(path: str) -> Response:
            del path
            return Response(status_code=404)

    return app


app = create_app()
