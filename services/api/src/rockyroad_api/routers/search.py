from __future__ import annotations

from fastapi import APIRouter, Query, Request

from rockyroad_api.models import RecentSearchOut, SearchResponse, Viewport
from rockyroad_api.search import list_recent_searches, record_recent_search, search_places

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
) -> SearchResponse:
    viewport = None
    if None not in {west, south, east, north}:
        viewport = Viewport(west=west or 0, south=south or 0, east=east or 0, north=north or 0)
    result = search_places(request.app.state.db, q, viewport)
    record_recent_search(request.app.state.db, q, result.results[0].id if result.results else None)
    return result


@router.get("/recent-searches", response_model=list[RecentSearchOut])
def recent_searches(request: Request) -> list[RecentSearchOut]:
    return list_recent_searches(request.app.state.db)
