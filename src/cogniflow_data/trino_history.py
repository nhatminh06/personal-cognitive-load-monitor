"""Read-only Trino adapter for a version-pinned Delta Silver snapshot."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

TABLE = "lakehouse.silver.session_features"
COLUMNS = (
    "event_id, session_id, schema_version, to_iso8601(event_time) AS event_time, "
    "to_iso8601(ingested_at) AS ingested_at, source, "
    "focus_minutes, distraction_minutes, tasks_due, hours_to_deadline, "
    "focus_ratio, distraction_ratio, kafka_topic, kafka_partition, kafka_offset"
)


class TrinoHistoryReader:
    def __init__(self, endpoint: str = "http://127.0.0.1:8081") -> None:
        if endpoint.rstrip("/") != "http://127.0.0.1:8081":
            raise ValueError("historical reads are restricted to local Trino on 127.0.0.1:8081")
        self.endpoint = endpoint.rstrip("/")
        self.session = requests.Session()

    def _query(self, sql: str) -> list[dict[str, Any]]:
        response = self.session.post(
            f"{self.endpoint}/v1/statement",
            data=sql.encode(),
            headers={"X-Trino-User": "cogniflow-history", "X-Trino-Time-Zone": "UTC"},
            timeout=10,
            allow_redirects=False,
        )
        rows: list[list[Any]] = []
        columns: list[str] = []
        while True:
            if response.is_redirect or response.is_permanent_redirect:
                raise RuntimeError("Trino redirects are forbidden")
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise RuntimeError(body["error"]["message"])
            if body.get("columns"):
                columns = [column["name"] for column in body["columns"]]
            rows.extend(body.get("data", []))
            next_uri = body.get("nextUri")
            if not next_uri:
                break
            parsed = urlparse(next_uri)
            if (parsed.scheme, parsed.hostname, parsed.port) != ("http", "127.0.0.1", 8081):
                raise RuntimeError("Trino returned an unsafe pagination URL")
            response = self.session.get(next_uri, timeout=10, allow_redirects=False)
        return [dict(zip(columns, row)) for row in rows]

    def snapshot(self, version: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if type(version) is not int or version < 0:
            raise ValueError("Delta version must be a non-negative integer")
        history = self._query(
            f'SELECT version, to_iso8601(timestamp) AS timestamp, operation '
            f'FROM lakehouse.silver."session_features$history" '
            f"WHERE version = {int(version)}"
        )
        if len(history) != 1:
            raise ValueError(f"Delta version {version} is unavailable")
        rows = self._query(f"SELECT {COLUMNS} FROM {TABLE} FOR VERSION AS OF {int(version)}")
        return history[0], rows
