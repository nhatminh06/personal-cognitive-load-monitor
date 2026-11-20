"""Collect Trino/dbt Gold row and physical-byte evidence after a successful build."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GOLD_TABLES = (
    "gold_daily_focus_metrics",
    "gold_data_quality_summary",
    "gold_deadline_pressure",
    "gold_distraction_trends",
    "gold_session_summary",
    "gold_workload_patterns",
)


def integer(value: object) -> int:
    if not isinstance(value, (int, str)):
        raise ValueError("Trino integer evidence has an invalid type")
    return int(value)


def query(endpoint: str, sql: str) -> list[list[object]]:
    rows: list[list[object]] = []
    request = Request(endpoint, data=sql.encode(), headers={"X-Trino-User": "cogniflow-benchmark"})
    try:
        while True:
            with urlopen(request, timeout=30) as response:
                page = json.loads(response.read())
            if "error" in page:
                raise RuntimeError(page["error"].get("message", "Trino query failed"))
            rows.extend(page.get("data", []))
            if "nextUri" not in page:
                return rows
            request = Request(page["nextUri"], headers={"X-Trino-User": "cogniflow-benchmark"})
    except (HTTPError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError("Trino evidence query failed") from error


def collect(endpoint: str, s3: Any | None = None, bucket: str | None = None) -> dict[str, object]:
    if s3 is None:
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:9000"),
            aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
            aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
            region_name="us-east-1",
            config=Config(s3={"addressing_style": "path"}),
        )
    bucket = bucket or os.getenv("MINIO_LAKEHOUSE_BUCKET", "cogniflow-lakehouse")
    accepted = query(
        endpoint,
        "SELECT accepted_rows FROM lakehouse.gold.gold_data_quality_summary "
        "ORDER BY measured_at DESC LIMIT 1",
    )
    if len(accepted) != 1 or len(accepted[0]) != 1:
        raise ValueError("Gold accepted-row evidence is incomplete")
    physical = 0
    table_rows: dict[str, int] = {}
    for table in GOLD_TABLES:
        counts = query(endpoint, f"SELECT count(*) FROM lakehouse.gold.{table}")
        if len(counts) != 1:
            raise ValueError(f"Gold evidence is incomplete for {table}")
        table_rows[table] = integer(counts[0][0])
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="metastore/gold/"):
        physical += sum(integer(item["Size"]) for item in page.get("Contents", []))
    return {
        "schema_version": "1.0",
        "status": "gold_complete",
        "accepted_rows": integer(accepted[0][0]),
        "table_rows": table_rows,
        "gold_physical_bytes": physical,
    }


def write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8081/v1/statement")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = collect(args.endpoint)
        write(args.output, result)
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
