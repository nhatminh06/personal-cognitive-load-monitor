"""Publish one bounded focus-session outbox batch to Kafka."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cogniflow_data.kafka import KafkaPublisher
from cogniflow_sessions import FocusSessionRepository, publish_pending


def main() -> None:
    published = publish_pending(FocusSessionRepository(), KafkaPublisher(), limit=25)
    print(f"published={published}")


if __name__ == "__main__":
    main()
