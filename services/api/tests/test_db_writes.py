from __future__ import annotations

from typing import Any

import pytest

from rockyroad_api.db import Database
from rockyroad_api.models import TripCreate
from rockyroad_api.trips import create_trip, list_trips


def test_failed_write_rolls_back(db: Database) -> None:
    create_trip(db, TripCreate(name="Keep me"))

    def boom(conn: Any) -> None:
        conn.execute(
            "INSERT INTO trips VALUES (?, 'Broken', now(), now())",
            ["11111111-1111-1111-1111-111111111111"],
        )
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        db.write(boom)
    names = [trip.name for trip in list_trips(db)]
    assert names == ["Keep me"]
