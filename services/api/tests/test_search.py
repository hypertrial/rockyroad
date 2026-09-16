from __future__ import annotations

from rockyroad_api.models import Viewport
from rockyroad_api.search import rank_rows


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
