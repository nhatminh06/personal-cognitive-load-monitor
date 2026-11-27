"""TLS gateway entrypoint for a private, single-host sidecar deployment candidate."""

from __future__ import annotations

import json
import os
import signal
import ssl
import threading
from pathlib import Path

from .kafka_gateway import KafkaGateway


def main():
    cert = Path(os.environ["GATEWAY_TLS_CERT_FILE"])
    key = Path(os.environ["GATEWAY_TLS_KEY_FILE"])
    secret_file = Path(os.environ["GATEWAY_SECRETS_FILE"])
    secrets = json.loads(secret_file.read_text())
    if (not isinstance(secrets, dict) or not secrets or
            any(not isinstance(k, str) or not isinstance(v, str) or len(v) < 32
                for k, v in secrets.items())):
        raise ValueError("invalid secret file")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    gateway = KafkaGateway(secret=next(iter(secrets.values())), secrets=secrets,
                           broker=os.environ["GATEWAY_KAFKA_BROKER"],
                           topic=os.environ["GATEWAY_KAFKA_TOPIC"],
                           database=Path(os.environ["GATEWAY_DATABASE_FILE"]),
                           tls_context=context).start()
    done = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    signal.signal(signal.SIGINT, lambda *_: done.set())
    try:
        done.wait()
    finally:
        gateway.close()


if __name__ == "__main__":
    main()
