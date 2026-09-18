from __future__ import annotations

import json
from typing import Any

import httpx

from rockyroad_api.models import Maneuver, RouteAlternative, StopOut, TripSettingsOut
from rockyroad_api.providers import redact_secret
from rockyroad_api.routing import RouteComputation, RoutingError
from rockyroad_api.settings import Settings

MAX_ORS_STOPS = 50
ORS_PROFILE = "driving-car"


def ors_avoid_features(settings: TripSettingsOut) -> list[str]:
    features: list[str] = []
    if settings.avoid_tolls:
        features.append("tollways")
    if settings.avoid_highways:
        features.append("highways")
    if settings.avoid_ferries:
        features.append("ferries")
    return features


def ors_directions_payload(stops: list[StopOut], settings: TripSettingsOut) -> dict[str, Any]:
    body: dict[str, Any] = {
        "coordinates": [[stop.lon, stop.lat] for stop in stops],
        "instructions": True,
        "geometry": True,
        "units": "m",
    }
    avoided = ors_avoid_features(settings)
    if avoided:
        body["options"] = {"avoid_features": avoided}
    return body


def ors_optimization_payload(stops: list[StopOut]) -> dict[str, Any]:
    first, last = stops[0], stops[-1]
    return {
        "vehicles": [
            {
                "id": 1,
                "profile": ORS_PROFILE,
                "start": [first.lon, first.lat],
                "end": [last.lon, last.lat],
            }
        ],
        "jobs": [{"id": index, "location": [stop.lon, stop.lat]} for index, stop in enumerate(stops[1:-1], start=1)],
    }


def parse_ors_geojson(payload: dict[str, Any]) -> list[RouteAlternative]:
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise RoutingError("OpenRouteService returned a route without geometry", status_code=502)
    feature = features[0]
    if not isinstance(feature, dict):
        raise RoutingError("OpenRouteService returned a route without geometry", status_code=502)
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise RoutingError("OpenRouteService returned a route without geometry", status_code=502)
    raw_coordinates = geometry.get("coordinates")
    if not isinstance(raw_coordinates, list):
        raise RoutingError("OpenRouteService returned a route without geometry", status_code=502)
    coordinates: list[list[float]] = []
    for point in raw_coordinates:
        if not isinstance(point, list) or len(point) < 2:
            raise RoutingError("OpenRouteService returned a route without geometry", status_code=502)
        try:
            coordinates.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError) as exc:
            raise RoutingError("OpenRouteService returned a route without geometry", status_code=502) from exc
    raw_properties = feature.get("properties")
    properties: dict[str, Any] = raw_properties if isinstance(raw_properties, dict) else {}
    raw_summary = properties.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    maneuvers: list[Maneuver] = []
    for segment in properties.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        for step in segment.get("steps") or []:
            if not isinstance(step, dict):
                continue
            way_points = step.get("way_points") or [0]
            begin = int(way_points[0]) if isinstance(way_points, list) and way_points else 0
            maneuvers.append(
                Maneuver(
                    instruction=str(step.get("instruction") or ""),
                    type=step.get("type") if isinstance(step.get("type"), int) else None,
                    distance_m=float(step.get("distance") or 0.0),
                    duration_s=float(step.get("duration") or 0.0),
                    begin_shape_index=begin,
                )
            )
    return [
        RouteAlternative(
            index=0,
            distance_m=float(summary.get("distance") or 0.0),
            duration_s=float(summary.get("duration") or 0.0),
            geometry={"type": "LineString", "coordinates": coordinates},
            maneuvers=maneuvers,
        )
    ]


def parse_vroom_order(payload: dict[str, Any], stop_count: int) -> list[int]:
    unassigned = payload.get("unassigned") or []
    if unassigned:
        raise RoutingError("OpenRouteService could not include every stop in the optimized order", status_code=422)
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise RoutingError("OpenRouteService did not return an optimized stop order", status_code=422)
    steps = routes[0].get("steps") if isinstance(routes[0], dict) else None
    if not isinstance(steps, list):
        raise RoutingError("OpenRouteService did not return an optimized stop order", status_code=422)
    expected = set(range(1, stop_count - 1))
    seen: list[int] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "job":
            continue
        job_id = step.get("id")
        if not isinstance(job_id, int):
            raise RoutingError("OpenRouteService returned an incomplete optimized stop order", status_code=422)
        seen.append(job_id)
    if len(seen) != len(expected) or set(seen) != expected:
        raise RoutingError("OpenRouteService returned an incomplete optimized stop order", status_code=422)
    return [0, *seen, stop_count - 1]


def ors_failure_message(status_code: int, body: str, *, secret: str) -> tuple[str, int]:
    safe = redact_secret(body, secret).strip()
    lowered = safe.casefold()
    error_code: int | None = None
    try:
        payload = json.loads(safe)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), int):
            error_code = error["code"]
    if status_code in {401, 403} and any(token in lowered for token in ("quota", "limit", "exceed", "rate")):
        return "OpenRouteService daily quota is exhausted. Try again later.", 429
    if status_code == 401:
        return "OpenRouteService rejected the API key.", 503
    if status_code == 403:
        return "OpenRouteService denied the request. Check the API key or daily quota.", 503
    if status_code == 429:
        return "OpenRouteService rate limit reached. Wait a minute and try again.", 429
    if error_code in {2009, 2016} or any(
        token in lowered for token in ("could not find routable", "route could not be found", "unable to find a route")
    ):
        message = "OpenRouteService could not connect those stops by road. Move a stop to a nearby road and try again."
        return message, 422
    if error_code in {2010, 2013, 2014, 2015} or "point was not found" in lowered:
        return "No roads near those stops in OpenRouteService coverage.", 422
    if error_code in {2004, 2017} or status_code == 413:
        return "That route exceeds an OpenRouteService request limit.", 422
    if 400 <= status_code < 500:
        return "OpenRouteService rejected RockyRoad's route request.", 502
    return "OpenRouteService could not produce a route.", 503


class OpenRouteServiceClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.ors_timeout_s)

    def request_route(self, stops: list[StopOut], settings: TripSettingsOut) -> RouteComputation:
        if len(stops) < 2:
            raise RoutingError("at least two stops are required to build a route", status_code=400)
        if len(stops) > MAX_ORS_STOPS:
            raise RoutingError(f"OpenRouteService accepts at most {MAX_ORS_STOPS} stops.", status_code=422)
        if not self.settings.has_ors_key():
            raise RoutingError("OpenRouteService API key is missing. Set ROCKYROAD_ORS_API_KEY.", status_code=503)
        ordered = list(stops)
        optimized_order: list[int] | None = None
        if settings.optimize and len(stops) >= 3:
            optimized_order = parse_vroom_order(self._optimize(stops), len(stops))
            ordered = [stops[index] for index in optimized_order]
        alternatives = parse_ors_geojson(self._directions(ordered, settings))
        return RouteComputation(alternatives=alternatives, optimized_order=optimized_order)

    def _headers(self, *, accept: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": self.settings.ors_key_value(),
            "Content-Type": "application/json",
            "Accept": accept,
        }

    def _post(self, url: str, body: dict[str, Any], *, accept: str = "application/json") -> dict[str, Any]:
        secret = self.settings.ors_key_value()
        try:
            response = self.client.post(url, json=body, headers=self._headers(accept=accept))
        except httpx.TimeoutException as exc:
            raise RoutingError("OpenRouteService timed out.", status_code=503) from exc
        except httpx.HTTPError as exc:
            raise RoutingError("OpenRouteService is unavailable.", status_code=503) from exc
        if response.status_code >= 400:
            message, status = ors_failure_message(response.status_code, response.text, secret=secret)
            raise RoutingError(message, status_code=status)
        try:
            payload = response.json()
        except ValueError as exc:
            raise RoutingError("OpenRouteService returned an unreadable response.", status_code=502) from exc
        if not isinstance(payload, dict):
            raise RoutingError("OpenRouteService returned an unreadable response.", status_code=502)
        return payload

    def _directions(self, stops: list[StopOut], settings: TripSettingsOut) -> dict[str, Any]:
        url = f"{self.settings.ors_base_url.rstrip('/')}/v2/directions/{ORS_PROFILE}/geojson"
        return self._post(url, ors_directions_payload(stops, settings), accept="application/geo+json")

    def _optimize(self, stops: list[StopOut]) -> dict[str, Any]:
        return self._post(self.settings.ors_optimization_url, ors_optimization_payload(stops))
