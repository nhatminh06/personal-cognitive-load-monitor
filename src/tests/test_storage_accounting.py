from __future__ import annotations

import pytest

from cogniflow_data.storage_accounting import list_objects, prefix_evidence


class S3:
    def __init__(self, *, missing_token: bool = False):
        self.calls = []
        self.missing_token = missing_token

    def list_objects_v2(self, **request):
        self.calls.append(request)
        if "ContinuationToken" not in request:
            page = {"Contents": [{"Key": "a", "Size": 10}], "IsTruncated": True}
            if not self.missing_token:
                page["NextContinuationToken"] = "next"
            return page
        return {"Contents": [{"Key": "b", "Size": 20}], "IsTruncated": False}


def test_storage_accounting_paginates_and_preserves_physical_byte_units() -> None:
    client = S3()
    assert prefix_evidence(client, "bronze", "session_events/") == {"objects": 2, "bytes": 30}
    assert client.calls[1]["ContinuationToken"] == "next"


def test_storage_accounting_rejects_unresumable_listing() -> None:
    with pytest.raises(RuntimeError, match="continuation"):
        list_objects(S3(missing_token=True), "bronze", "session_events/")
