"""Deterministic, bounded Module II synthetic event generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cogniflow_data.events import EventProvenance, SessionEvent  # noqa: E402

PROFILES = {"tiny": 10, "small": 1_000, "medium": 100_000, "large": 1_000_000}


def event(index: int, randomizer: random.Random, start: datetime) -> SessionEvent:
    focus = randomizer.randint(0, 180)
    distraction = randomizer.randint(0, 90)
    return SessionEvent(
        event_id=UUID(int=index + 1), session_id=f"synthetic-{index % 100:03d}",
        event_time=start + timedelta(seconds=index), ingested_at=start + timedelta(seconds=index), source="synthetic-generator",
        payload={"focus_minutes": focus, "distraction_minutes": distraction,
                 "tasks_due": randomizer.randint(0, 20), "hours_to_deadline": randomizer.uniform(1, 168)},
        provenance=EventProvenance(producer="generate_session_events", producer_version="1.0"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES, default="tiny")
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=100_000_000)
    args = parser.parse_args()
    count = args.count if args.count is not None else PROFILES[args.profile]
    if count < 0 or args.max_bytes <= 0:
        parser.error("count must be non-negative and max-bytes must be positive")
    randomizer = random.Random(args.seed)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    digest = hashlib.sha256()
    written = 0
    with args.output.open("wb") as stream:
        for index in range(count):
            line = event(index, randomizer, start).wire_bytes() + b"\n"
            if written + len(line) > args.max_bytes:
                raise RuntimeError("maximum output size would be exceeded")
            stream.write(line)
            digest.update(line)
            written += len(line)
    print(json.dumps({"records": count, "bytes": written, "sha256": digest.hexdigest(), "seed": args.seed}))


if __name__ == "__main__":
    main()
