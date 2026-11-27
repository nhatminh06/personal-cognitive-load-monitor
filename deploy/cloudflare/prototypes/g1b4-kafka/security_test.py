"""Gateway rejects non-synthetic payloads before contacting Kafka."""

import secrets
import tempfile
import unittest
from pathlib import Path

from gateway import KafkaGateway
from consumer import reconcile
from integration_test import direct, envelope, event


class GatewaySecurityTest(unittest.TestCase):
    def test_reconciliation_flags_missing_and_duplicate_ids(self):
        result = reconcile(["a", "b"], ["a"], ["a"], ["a", "a"])
        self.assertEqual(result["missing_receipts"], ["b"])
        self.assertEqual(result["duplicate_attempt_ids"], ["a"])

    def test_non_synthetic_source_and_subject_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cogniflow-g1b4-security-") as temp:
            secret = secrets.token_hex(32)
            gateway = KafkaGateway(secret=secret, broker="127.0.0.1:39094",
                                   topic="g1b4-synthetic-security", database=Path(temp) / "gateway.sqlite").start()
            try:
                self.assertEqual(direct(gateway, secret, envelope({**event(1), "source": "personal"})), 422)
                self.assertEqual(direct(gateway, secret, envelope({**event(2), "subject_id": "person"})), 422)
                self.assertEqual(direct(gateway, secret, envelope(event(3)), valid=False), 401)
            finally:
                gateway.close()

    def test_gateway_rate_window_rejects_excess_requests_before_kafka(self):
        with tempfile.TemporaryDirectory(prefix="cogniflow-g1d2-rate-") as temp:
            secret = secrets.token_hex(32)
            gateway = KafkaGateway(secret=secret, broker="127.0.0.1:39094",
                                   topic="g1b4-synthetic-security", database=Path(temp) / "gateway.sqlite",
                                   max_requests=1).start()
            try:
                self.assertEqual(direct(gateway, secret, envelope(event(1)), valid=False), 401)
                self.assertEqual(direct(gateway, secret, envelope(event(2)), valid=False), 429)
            finally:
                gateway.close()


if __name__ == "__main__":
    unittest.main()
