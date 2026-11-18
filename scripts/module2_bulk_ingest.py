"""Run bounded, restart-safe Module II source → Kafka → Bronze ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cogniflow_data.bronze import BronzeStore  # noqa: E402
from cogniflow_data.bulk import BulkConfig, ingest, validate_resources  # noqa: E402
from cogniflow_data.kafka import KafkaPublisher  # noqa: E402


def available_memory() -> int:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0]) * 1024
    return values["MemAvailable"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--batch-records", type=int, default=5_000)
    parser.add_argument("--max-source-bytes", type=int, default=110_000_000_000)
    parser.add_argument("--min-free-bytes", type=int, default=20_000_000_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-over-100gb", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("bulk ingestion requires --execute")
    config = BulkConfig(args.batch_records, args.max_source_bytes, args.min_free_bytes)
    try:
        manifest = json.loads((args.dataset / "manifest.json").read_text())
        validate_resources(args.dataset, int(manifest["committed_bytes"]), config, available_memory())
        report = ingest(
            args.dataset,
            args.checkpoint,
            args.report,
            KafkaPublisher(),
            BronzeStore(),
            config,
            resume=args.resume,
            allow_over_100gb=args.allow_over_100gb,
        )
    except (KeyError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
