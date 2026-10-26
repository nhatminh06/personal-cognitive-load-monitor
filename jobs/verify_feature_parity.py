"""Execute shared feature fixtures through real Spark expressions."""

from __future__ import annotations

import json
from pathlib import Path

from pyspark.sql import SparkSession

from bronze_to_silver import add_features
from preprocessing_api.features import FEATURE_NAMES


def main() -> None:
    fixtures = json.loads(Path("tests/fixtures/feature_vectors.json").read_text())
    spark = (
        SparkSession.builder.master("local[1]")
        .appName("cogniflow-feature-parity")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        rows = [{**case["input"], "event_time": case["event_time"]} for case in fixtures]
        actual = add_features(spark.createDataFrame(rows)).select(*FEATURE_NAMES, "event_time").collect()
        assert len(actual) == len(fixtures)
        for case, row in zip(fixtures, actual):
            assert case["feature_schema_version"] == "1.0"
            assert tuple(case["feature_names"]) == FEATURE_NAMES
            for name, expected in zip(FEATURE_NAMES, case["expected"]):
                assert abs(float(row[name]) - expected) <= 1e-12, (name, row[name], expected)
            assert row.event_time == case["event_time"]
        print(json.dumps({"engine": "spark", "cases": len(fixtures), "status": "passed"}))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
