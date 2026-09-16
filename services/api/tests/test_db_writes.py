from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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


def test_concurrent_reads_and_writes(db: Database) -> None:
    create_trip(db, TripCreate(name="Seed"))
    writer_count = 8

    def write_one(index: int) -> str:
        return create_trip(db, TripCreate(name=f"Writer {index}")).name

    def read_many() -> int:
        total = 0
        for _ in range(20):
            total += len(list_trips(db))
        return total

    with ThreadPoolExecutor(max_workers=6) as pool:
        write_futures = [pool.submit(write_one, index) for index in range(writer_count)]
        read_futures = [pool.submit(read_many) for _ in range(4)]
        written = [future.result() for future in as_completed(write_futures)]
        read_totals = [future.result() for future in as_completed(read_futures)]

    assert len(written) == writer_count
    assert all(total > 0 for total in read_totals)
    names = {trip.name for trip in list_trips(db)}
    assert names == {"Seed", *{f"Writer {index}" for index in range(writer_count)}}
