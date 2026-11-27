"""Reject unsupported Cloudflare event shapes before Kafka routing."""

import hashlib
import json
import secrets
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g1b4-kafka"))
from gateway import KafkaGateway  # noqa: E402
from integration_test import direct, event  # noqa: E402


def wire(item):
    payload = json.dumps(item, separators=(",", ":"))
    return {"event_id": item["event_id"], "session_id": item["session_id"],
            "sequence": item.get("sequence", 0),
            "digest": hashlib.sha256(payload.encode()).hexdigest(), "payload": payload}


class RouteValidationTest(unittest.TestCase):
    def test_invalid_lifecycle_behavioral_and_effort_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cogniflow-g1b5-routing-") as temp:
            secret = secrets.token_hex(32)
            gateway = KafkaGateway(secret=secret, broker="127.0.0.1:29092",
                                   topic="g1b4-g1b5-test", database=Path(temp) / "gateway.sqlite",
                                   behavioral_topic="cogniflow.behavioral-activity.v1").start()
            try:
                lifecycle = {**event(1), "session_kind": "invalid"}
                behavioral = {**event(2), "event_type": "behavioral.window", "sequence": 0}
                effort = {**event(3), "event_type": "effort.reported", "sequence": 0}
                for item in (lifecycle, behavioral, effort):
                    self.assertEqual(direct(gateway, secret, wire(item)), 422)
            finally:
                gateway.close()


if __name__ == "__main__":
    unittest.main()
