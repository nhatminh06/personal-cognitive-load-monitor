"""Deterministic, bounded Module II synthetic event generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cogniflow_data.events import SESSION_TOPIC, EventProvenance, SessionEvent  # noqa: E402
from cogniflow_data.kafka import KafkaPublisher  # noqa: E402

PROFILES = {"tiny": 10, "small": 1_000, "medium": 100_000, "large": 1_000_000}


def event(
    index: int,
    randomizer: random.Random,
    start: datetime,
    session_count: int = 100,
    id_offset: int = 0,
) -> SessionEvent:
    focus = randomizer.randint(0, 180)
    distraction = randomizer.randint(0, 90)
    return SessionEvent(
        event_id=UUID(int=id_offset + index + 1), session_id=f"synthetic-{index % session_count:03d}",
        event_time=start + timedelta(seconds=index), ingested_at=start + timedelta(seconds=index), source="synthetic-generator",
        payload={"focus_minutes": focus, "distraction_minutes": distraction,
                 "tasks_due": randomizer.randint(0, 20), "hours_to_deadline": randomizer.uniform(1, 168)},
        provenance=EventProvenance(producer="generate_session_events", producer_version="1.0"),
    )


def event_bytes(
    index: int,
    seed: int,
    start: datetime,
    *,
    late_every: int = 0,
    late_by_seconds: int = 300,
    invalid: bool = False,
    session_count: int = 100,
    id_offset: int = 0,
) -> bytes:
    """Build one independently reproducible fixture record."""

    item = event(index, random.Random(seed + index), start, session_count, id_offset)
    if late_every and (index + 1) % late_every == 0:
        item.event_time -= timedelta(seconds=late_by_seconds)
    if not invalid:
        return item.wire_bytes()
    raw = item.model_dump(mode="json")
    raw["payload"]["focus_minutes"] = -1
    return json.dumps(raw, separators=(",", ":")).encode()


def _write_state(path: Path, next_index: int) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"next_index": next_index}) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES, default="tiny")
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--session-count", type=int, default=100)
    parser.add_argument("--id-offset", type=int, default=0)
    parser.add_argument("--start", default="2026-01-01T00:00:00+00:00")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=100_000_000)
    parser.add_argument("--min-free-bytes", type=int, default=1_000_000_000)
    parser.add_argument("--duplicate-every", type=int, default=0)
    parser.add_argument("--invalid-every", type=int, default=0)
    parser.add_argument("--late-every", type=int, default=0)
    parser.add_argument("--late-by-seconds", type=int, default=300)
    parser.add_argument("--publish-kafka", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--state-file", type=Path)
    args = parser.parse_args()
    count = args.count if args.count is not None else PROFILES[args.profile]
    bounded = (args.duplicate_every, args.invalid_every, args.late_every)
    if (count < 0 or args.session_count <= 0 or args.max_bytes <= 0
            or args.min_free_bytes < 0 or any(x < 0 for x in bounded)):
        parser.error("counts and intervals must be non-negative; max-bytes must be positive")
    if args.late_by_seconds < 0:
        parser.error("late-by-seconds must be non-negative")
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    if start.tzinfo is None or start.utcoffset() is None:
        parser.error("start must include a timezone")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    state_file = args.state_file or args.output.with_suffix(args.output.suffix + ".state.json")
    start_index = 0
    if args.resume:
        if not args.output.exists() or not state_file.exists():
            parser.error("resume requires both the output and state files")
        start_index = int(json.loads(state_file.read_text())["next_index"])
    elif args.output.exists():
        args.output.unlink()
    if start_index > count:
        parser.error("resume state is beyond requested count")

    digest = hashlib.sha256()
    written = args.output.stat().st_size if args.output.exists() else 0
    if args.output.exists():
        digest.update(args.output.read_bytes())
    publisher = KafkaPublisher() if args.publish_kafka else None
    emitted = 0
    with args.output.open("ab") as stream:
        for index in range(start_index, count):
            invalid = bool(args.invalid_every and (index + 1) % args.invalid_every == 0)
            payload = event_bytes(
                index,
                args.seed,
                start,
                late_every=args.late_every,
                late_by_seconds=args.late_by_seconds,
                invalid=invalid,
                session_count=args.session_count,
                id_offset=args.id_offset,
            )
            copies = 2 if args.duplicate_every and (index + 1) % args.duplicate_every == 0 else 1
            for _ in range(copies):
                line = payload + b"\n"
                if written + len(line) > args.max_bytes:
                    raise RuntimeError("maximum output size would be exceeded")
                if shutil.disk_usage(args.output.parent).free - len(line) < args.min_free_bytes:
                    raise RuntimeError("minimum free disk reserve would be violated")
                stream.write(line)
                stream.flush()
                digest.update(line)
                written += len(line)
                emitted += 1
                if publisher is not None:
                    if invalid:
                        key = f"synthetic-{index % args.session_count:03d}".encode()
                        publisher.publish_bytes(payload, key, SESSION_TOPIC)
                    else:
                        publisher.publish(SessionEvent.model_validate_json(payload), SESSION_TOPIC)
            _write_state(state_file, index + 1)
    print(json.dumps({"source_records": count, "emitted_records": emitted, "bytes": written,
                      "sha256": digest.hexdigest(), "seed": args.seed, "next_index": count}))


if __name__ == "__main__":
    main()
