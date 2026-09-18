from __future__ import annotations

from rockyroad_api.db import Database
from rockyroad_api.models import Viewport
from rockyroad_api.search import rank_rows, search_places


def test_rank_prefers_important_nearby_city() -> None:
    viewport = Viewport(west=-64, south=46, east=-62, north=47)
    ranked = rank_rows(
        [
            {
                "name": "Tiny Hamlet",
                "bm25": 4.0,
                "importance": 0.2,
                "population_score": 0.1,
                "type_prior": 0.35,
                "lon": -70.0,
                "lat": 40.0,
            },
            {
                "name": "Charlottetown",
                "bm25": 3.5,
                "importance": 0.9,
                "population_score": 0.7,
                "type_prior": 1.0,
                "lon": -63.13,
                "lat": 46.24,
            },
        ],
        viewport,
    )
    assert ranked[0]["name"] == "Charlottetown"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_keeps_places_outside_viewport() -> None:
    viewport = Viewport(west=-123.3, south=49.1, east=-123.0, north=49.4)
    ranked = rank_rows(
        [
            {
                "name": "Charlottetown",
                "bm25": 4.0,
                "importance": 0.9,
                "population_score": 0.7,
                "type_prior": 1.0,
                "lon": -63.13,
                "lat": 46.24,
            }
        ],
        viewport,
    )
    assert ranked[0]["name"] == "Charlottetown"
    assert ranked[0]["distance_km"] > 0


def test_fallback_search_treats_like_metacharacters_literally(db: Database) -> None:
    rows = [
        ("percent", "Percent % Place", "percent % place"),
        ("underscore", "Under_score Place", "under_score place"),
        ("bang", "Bang! Place", "bang! place"),
        ("plain", "Plain Place", "plain place"),
    ]
    for place_id, name, normalized in rows:
        db.conn.execute(
            "INSERT INTO geo_features VALUES (?, 'test', ?, ?, ?, 'place', -63.13, 46.24, NULL, 0.1, 0.1, 0.1, NULL)",
            [place_id, name, normalized, normalized],
        )

    assert [result.id for result in search_places(db, "%").results] == ["percent"]
    assert [result.id for result in search_places(db, "_").results] == ["underscore"]
    assert [result.id for result in search_places(db, "!").results] == ["bang"]
