"""Generate an explicitly authorized, partitioned Module II benchmark dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_session_events import event_bytes  # noqa: E402

OVER_100_GB = 100_000_000_000
MAX_RECORD_BYTES = 2_048


@dataclass(frozen=True)
class Config:
    target_bytes: int
    max_bytes: int
    partition_bytes: int
    min_free_bytes: int
    seed: int
    start: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def validate(config: Config, output: Path, execute: bool, allow_over_100gb: bool) -> None:
    if config.target_bytes <= 0 or config.target_bytes > config.max_bytes:
        raise ValueError("target-bytes must be positive and no greater than max-bytes")
    if config.partition_bytes < 4_096 or config.partition_bytes > config.max_bytes:
        raise ValueError("partition-bytes must be between 4096 and max-bytes")
    if config.min_free_bytes < 0:
        raise ValueError("min-free-bytes must be non-negative")
    if config.target_bytes > OVER_100_GB and not allow_over_100gb:
        raise ValueError("targets over 100 GB require --allow-over-100gb")
    if not execute:
        raise ValueError("generation requires the explicit --execute flag")
    if output.exists() and not output.is_dir():
        raise ValueError("output must be a directory")


def _load_resume(output: Path, config: Config) -> tuple[list[dict[str, object]], int, int]:
    checkpoint = output / "checkpoint.json"
    manifest = output / "manifest.json"
    if not checkpoint.exists() or not manifest.exists():
        raise ValueError("resume requires checkpoint.json and manifest.json")
    state = json.loads(checkpoint.read_text())
    recorded = json.loads(manifest.read_text())
    if state["config"] != asdict(config) or recorded["config"] != asdict(config):
        raise ValueError("resume configuration does not match the existing run")
    for partial in output.glob("part-*.jsonl.tmp"):
        partial.unlink()
    partitions = recorded["partitions"]
    for item in partitions:
        path = output / str(item["file"])
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"resume integrity check failed: {path.name}")
    return partitions, int(state["bytes"]), int(state["next_index"])


def generate(output: Path, config: Config, *, execute: bool, allow_over_100gb: bool, resume: bool) -> dict[str, object]:
    validate(config, output, execute, allow_over_100gb)
    output.mkdir(parents=True, exist_ok=True)
    if resume:
        partitions, written, next_index = _load_resume(output, config)
        started_at = json.loads((output / "manifest.json").read_text())["started_at"]
    else:
        if any(output.iterdir()):
            raise ValueError("output directory must be empty unless --resume is used")
        partitions, written, next_index = [], 0, 0
        started_at = datetime.now(UTC).isoformat()
        atomic_json(
            output / "manifest.json",
            {"schema_version": "1.0", "config": asdict(config), "started_at": started_at, "partitions": []},
        )
        atomic_json(output / "checkpoint.json", {"config": asdict(config), "bytes": 0, "next_index": 0})

    event_start = datetime.fromisoformat(config.start)
    while written < config.target_bytes:
        intended = min(config.partition_bytes, config.target_bytes - written)
        if shutil.disk_usage(output).free - intended < config.min_free_bytes:
            raise RuntimeError("minimum free disk reserve would be violated")
        name = f"part-{len(partitions):06d}.jsonl"
        final_path = output / name
        temporary = final_path.with_suffix(".jsonl.tmp")
        partition_digest = hashlib.sha256()
        partition_written = 0
        rows = 0
        with temporary.open("xb") as stream:
            while partition_written < intended:
                payload = event_bytes(next_index, config.seed, event_start)
                line = payload + b"\n"
                if len(line) > MAX_RECORD_BYTES:
                    raise RuntimeError("generated record exceeds the bounded record size")
                remaining = intended - partition_written
                if remaining < len(line):
                    raise RuntimeError("partition size cannot fit one bounded record")
                if remaining - len(line) < MAX_RECORD_BYTES:
                    line = payload + (b" " * (remaining - len(line))) + b"\n"
                stream.write(line)
                partition_digest.update(line)
                partition_written += len(line)
                next_index += 1
                rows += 1
        temporary.replace(final_path)
        written += partition_written
        partitions.append({"file": name, "bytes": partition_written, "rows": rows, "sha256": partition_digest.hexdigest()})
        manifest = {"schema_version": "1.0", "config": asdict(config), "started_at": started_at, "partitions": partitions}
        atomic_json(output / "manifest.json", manifest)
        atomic_json(output / "checkpoint.json", {"config": asdict(config), "bytes": written, "next_index": next_index})

    completed_at = datetime.now(UTC).isoformat()
    report: dict[str, object] = {
        "status": "complete",
        "actual_bytes": written,
        "target_bytes": config.target_bytes,
        "rows": sum(cast(int, item["rows"]) for item in partitions),
        "partitions": len(partitions),
        "started_at": started_at,
        "completed_at": completed_at,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "manifest_sha256": sha256(output / "manifest.json"),
    }
    atomic_json(output / "benchmark-report.json", report)
    (output / "benchmark-summary.md").write_text(
        "# Module II benchmark generation\n\n"
        f"- Status: complete\n- Actual bytes: {written}\n- Rows: {report['rows']}\n"
        f"- Partitions: {len(partitions)}\n- Peak RSS KiB: {report['peak_rss_kib']}\n"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-bytes", type=int, required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    parser.add_argument("--partition-bytes", type=int, default=128_000_000)
    parser.add_argument("--min-free-bytes", type=int, default=20_000_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", default="2026-01-01T00:00:00+00:00")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-over-100gb", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = Config(args.target_bytes, args.max_bytes, args.partition_bytes, args.min_free_bytes, args.seed, args.start)
    try:
        print(json.dumps(generate(args.output, config, execute=args.execute, allow_over_100gb=args.allow_over_100gb, resume=args.resume), sort_keys=True))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
