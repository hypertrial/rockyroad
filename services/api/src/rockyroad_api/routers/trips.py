from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from rockyroad_api.models import (
    RouteResponse,
    SavedPlaceIn,
    SavedPlaceOut,
    StopIn,
    TripCreate,
    TripOut,
    TripSummary,
    TripUpdate,
)
from rockyroad_api.routing import RoutingError
from rockyroad_api.trips import (
    create_saved_place,
    create_trip,
    delete_saved_place,
    delete_trip,
    get_trip,
    list_saved_places,
    list_trips,
    replace_stops,
    route_trip,
    update_trip,
)

router = APIRouter(tags=["trips"])


@router.get("/trips", response_model=list[TripSummary])
def trips_index(request: Request) -> list[TripSummary]:
    return list_trips(request.app.state.db)


@router.post("/trips", response_model=TripOut, status_code=201)
def trips_create(request: Request, payload: TripCreate) -> TripOut:
    try:
        return create_trip(request.app.state.db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/trips/{trip_id}", response_model=TripOut)
def trips_get(request: Request, trip_id: UUID) -> TripOut:
    trip = get_trip(request.app.state.db, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return trip


@router.patch("/trips/{trip_id}", response_model=TripOut)
def trips_update(request: Request, trip_id: UUID, payload: TripUpdate) -> TripOut:
    trip = update_trip(request.app.state.db, trip_id, payload)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return trip


@router.delete("/trips/{trip_id}", status_code=204)
def trips_delete(request: Request, trip_id: UUID) -> Response:
    if not delete_trip(request.app.state.db, trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    return Response(status_code=204)


@router.put("/trips/{trip_id}/stops", response_model=TripOut)
def trips_replace_stops(request: Request, trip_id: UUID, stops: list[StopIn]) -> TripOut:
    try:
        trip = replace_stops(request.app.state.db, trip_id, stops)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return trip


@router.post("/trips/{trip_id}/route", response_model=RouteResponse)
def trips_route(request: Request, trip_id: UUID) -> RouteResponse:
    try:
        return route_trip(request.app.state.db, request.app.state.routing, trip_id)
    except RoutingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/trips/{trip_id}/optimize", response_model=RouteResponse)
def trips_optimize(request: Request, trip_id: UUID) -> RouteResponse:
    trip = get_trip(request.app.state.db, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")
    update_trip(
        request.app.state.db,
        trip_id,
        TripUpdate(settings=trip.settings.model_copy(update={"optimize": True})),
    )
    try:
        return route_trip(request.app.state.db, request.app.state.routing, trip_id)
    except RoutingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/saved-places", response_model=list[SavedPlaceOut])
def saved_places_index(request: Request) -> list[SavedPlaceOut]:
    return list_saved_places(request.app.state.db)


@router.post("/saved-places", response_model=SavedPlaceOut, status_code=201)
def saved_places_create(request: Request, payload: SavedPlaceIn) -> SavedPlaceOut:
    try:
        return create_saved_place(request.app.state.db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/saved-places/{place_id}", status_code=204)
def saved_places_delete(request: Request, place_id: UUID) -> Response:
    if not delete_saved_place(request.app.state.db, place_id):
        raise HTTPException(status_code=404, detail="saved place not found")
    return Response(status_code=204)
