from __future__ import annotations

from rockyroad_data.places import dataset_for, feature_type, normalize_name, rows_from_export


def test_feature_classification() -> None:
    assert feature_type({"place": "town"}) == "town"
    assert feature_type({"tourism": "camp_site"}) == "campsite"
    assert dataset_for("fuel") == "fuel"
    assert normalize_name("  Charlottetown ") == "charlottetown"


def test_rows_from_geojsonseq(tmp_path) -> None:
    export = tmp_path / "features.geojsonseq"
    export.write_text(
        '{"type":"Feature","properties":{"name":"Charlottetown","place":"city","population":"38000","@id":"node/1"},"geometry":{"type":"Point","coordinates":[-63.13,46.24]}}\n',
        encoding="utf-8",
    )
    buckets = rows_from_export(export, {"city": 1.0, "other": 0.2})
    assert buckets["places"][0]["name"] == "Charlottetown"
    assert buckets["places"][0]["importance"] > 0.5
