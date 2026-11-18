"""Bounded S3 object inventory used by distributed processing evidence."""

from __future__ import annotations

from typing import Any


def list_objects(client: Any, bucket: str, prefix: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    token = None
    while True:
        request = {"Bucket": bucket, "Prefix": prefix}
        if token:
            request["ContinuationToken"] = token
        page = client.list_objects_v2(**request)
        objects.extend(page.get("Contents", []))
        if not page.get("IsTruncated"):
            return objects
        token = page.get("NextContinuationToken")
        if not token:
            raise RuntimeError("S3 listing was truncated without a continuation token")


def prefix_evidence(client: Any, bucket: str, prefix: str) -> dict[str, int]:
    objects = list_objects(client, bucket, prefix)
    return {
        "objects": len(objects),
        "bytes": sum(int(item.get("Size", 0)) for item in objects),
    }
