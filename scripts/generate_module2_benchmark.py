"""Generate an explicitly authorized, crash-consistent Module II dataset."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import resource
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_session_events import event_bytes  # noqa: E402

OVER_100_GB = 100_000_000_000
MAX_RECORD_BYTES = 2_048
Fault = Callable[[str], None]


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


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def directory_lock(output: Path) -> Iterator[None]:
    lock = (output / ".generator.lock").open("a+b")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another benchmark generator owns this output directory") from error
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _write_manifest(output: Path, manifest: dict[str, object], fault: Fault | None = None) -> None:
    target = output / "manifest.json"
    temporary = output / "manifest.json.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    if fault:
        fault("after_manifest_temp_fsync")
    os.replace(temporary, target)
    if fault:
        fault("after_manifest_replace")
    _fsync_directory(output)


def _initial_manifest(config: Config) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "config": asdict(config),
        "started_at": datetime.now(UTC).isoformat(),
        "committed_bytes": 0,
        "committed_rows": 0,
        "next_index": 0,
        "partitions": [],
    }


def _load_manifest(output: Path, config: Config, resume: bool) -> dict[str, object]:
    target = output / "manifest.json"
    temporary = output / "manifest.json.tmp"
    if not target.exists() and temporary.exists():
        try:
            candidate = json.loads(temporary.read_text())
        except json.JSONDecodeError:
            candidate = None
        if candidate and candidate.get("config") == asdict(config):
            os.replace(temporary, target)
            _fsync_directory(output)
        elif not list(output.glob("part-*.jsonl")):
            temporary.unlink()
            _fsync_directory(output)
        else:
            raise ValueError("interrupted manifest is not recoverable")
    elif target.exists() and temporary.exists():
        temporary.unlink()
        _fsync_directory(output)

    if not target.exists():
        if resume:
            raise ValueError("resume requires a committed manifest")
        if any(path.name != ".generator.lock" for path in output.iterdir()):
            raise ValueError("output directory must be empty unless --resume is used")
        manifest = _initial_manifest(config)
        _write_manifest(output, manifest)
        return manifest
    try:
        manifest = json.loads(target.read_text())
    except json.JSONDecodeError as error:
        raise ValueError("committed manifest is unreadable") from error
    if not resume:
        raise ValueError("output directory must be empty unless --resume is used")
    if manifest.get("schema_version") != "2.0" or manifest.get("config") != asdict(config):
        raise ValueError("resume configuration does not match the committed manifest")
    return manifest


def _verify_partition(path: Path, config: Config, start_index: int) -> dict[str, object]:
    digest = hashlib.sha256()
    identifiers = hashlib.sha256()
    size = 0
    rows = 0
    event_start = datetime.fromisoformat(config.start)
    with path.open("rb") as stream:
        for line in stream:
            size += len(line)
            digest.update(line)
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"deterministic event mismatch in {path.name}") from error
            identifier = payload.get("event_id")
            if not isinstance(identifier, str):
                raise ValueError(f"missing event ID in {path.name}")
            expected = event_bytes(start_index + rows, config.seed, event_start)
            if line.rstrip() != expected:
                raise ValueError(f"deterministic event mismatch in {path.name}")
            identifiers.update(identifier.encode())
            rows += 1
    if not rows:
        raise ValueError(f"empty partition: {path.name}")
    return {
        "file": path.name,
        "bytes": size,
        "rows": rows,
        "start_index": start_index,
        "next_index": start_index + rows,
        "sha256": digest.hexdigest(),
        "event_ids_sha256": identifiers.hexdigest(),
    }


def _reconcile(output: Path, config: Config, manifest: dict[str, object]) -> dict[str, object]:
    removed_partial = False
    for partial in output.glob("part-*.jsonl.tmp"):
        partial.unlink()
        removed_partial = True
    if removed_partial:
        _fsync_directory(output)
    recorded = manifest.get("partitions")
    if not isinstance(recorded, list):
        raise ValueError("manifest partitions are invalid")
    verified: list[dict[str, object]] = []
    next_index = 0
    committed_bytes = 0
    for number, item in enumerate(recorded):
        if not isinstance(item, dict):
            raise ValueError("manifest partition metadata is invalid")
        expected_name = f"part-{number:06d}.jsonl"
        if item.get("file") != expected_name:
            raise ValueError("manifest partition sequence is invalid")
        path = output / expected_name
        if not path.is_file():
            raise ValueError(f"committed partition is missing: {expected_name}")
        actual = _verify_partition(path, config, next_index)
        if any(actual[key] != item.get(key) for key in actual):
            raise ValueError(f"committed partition metadata mismatch: {expected_name}")
        verified.append(actual)
        next_index = cast(int, actual["next_index"])
        committed_bytes += cast(int, actual["bytes"])

    orphan = output / f"part-{len(verified):06d}.jsonl"
    if orphan.exists():
        actual = _verify_partition(orphan, config, next_index)
        expected_size = min(config.partition_bytes, config.target_bytes - committed_bytes)
        if actual["bytes"] != expected_size:
            raise ValueError(f"orphan partition has unexpected size: {orphan.name}")
        verified.append(actual)
        next_index = cast(int, actual["next_index"])
        committed_bytes += cast(int, actual["bytes"])

    known = {cast(str, item["file"]) for item in verified}
    unexpected = sorted(path.name for path in output.glob("part-*.jsonl") if path.name not in known)
    if unexpected:
        raise ValueError(f"unexpected partitions require inspection: {', '.join(unexpected)}")
    if committed_bytes > config.target_bytes:
        raise ValueError("committed partitions exceed target-bytes")
    corrected = {
        **manifest,
        "committed_bytes": committed_bytes,
        "committed_rows": sum(cast(int, item["rows"]) for item in verified),
        "next_index": next_index,
        "partitions": verified,
    }
    return corrected


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


def _write_partition(output: Path, config: Config, number: int, start_index: int, intended: int, fault: Fault | None) -> None:
    final_path = output / f"part-{number:06d}.jsonl"
    temporary = output / f"part-{number:06d}.jsonl.tmp"
    if final_path.exists() or temporary.exists():
        raise ValueError(f"partition path already exists: {final_path.name}")
    event_start = datetime.fromisoformat(config.start)
    partition_written = 0
    index = start_index
    with temporary.open("xb") as stream:
        while partition_written < intended:
            payload = event_bytes(index, config.seed, event_start)
            line = payload + b"\n"
            if len(line) > MAX_RECORD_BYTES:
                raise RuntimeError("generated record exceeds the bounded record size")
            remaining = intended - partition_written
            if remaining < len(line):
                raise RuntimeError("partition size cannot fit one bounded record")
            if remaining - len(line) < MAX_RECORD_BYTES:
                line = payload + (b" " * (remaining - len(line))) + b"\n"
            stream.write(line)
            partition_written += len(line)
            index += 1
        stream.flush()
        os.fsync(stream.fileno())
    if fault:
        fault("after_partition_temp_fsync")
    os.link(temporary, final_path)
    temporary.unlink()
    _fsync_directory(output)
    if fault:
        fault("after_partition_publish")


def _write_report(output: Path, config: Config, manifest: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "complete",
        "actual_bytes": manifest["committed_bytes"],
        "target_bytes": config.target_bytes,
        "rows": manifest["committed_rows"],
        "partitions": len(cast(list[object], manifest["partitions"])),
        "unique_event_ids": manifest["committed_rows"],
        "next_index": manifest["next_index"],
        "started_at": manifest["started_at"],
        "completed_at": datetime.now(UTC).isoformat(),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "manifest_sha256": sha256(output / "manifest.json"),
    }
    report_path = output / "benchmark-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    with report_path.open("rb") as stream:
        os.fsync(stream.fileno())
    summary = output / "benchmark-summary.md"
    summary.write_text(
        "# Module II benchmark generation\n\n"
        f"- Status: complete\n- Actual bytes: {report['actual_bytes']}\n"
        f"- Rows / unique event IDs: {report['rows']}\n"
        f"- Partitions: {report['partitions']}\n- Next index: {report['next_index']}\n"
        f"- Peak RSS KiB: {report['peak_rss_kib']}\n"
    )
    with summary.open("rb") as stream:
        os.fsync(stream.fileno())
    _fsync_directory(output)
    return report


def generate(output: Path, config: Config, *, execute: bool, allow_over_100gb: bool, resume: bool, fault: Fault | None = None) -> dict[str, object]:
    validate(config, output, execute, allow_over_100gb)
    output.mkdir(parents=True, exist_ok=True)
    with directory_lock(output):
        loaded = _load_manifest(output, config, resume)
        manifest = _reconcile(output, config, loaded)
        if manifest != loaded:
            _write_manifest(output, manifest)
        while cast(int, manifest["committed_bytes"]) < config.target_bytes:
            written = cast(int, manifest["committed_bytes"])
            intended = min(config.partition_bytes, config.target_bytes - written)
            if shutil.disk_usage(output).free - intended < config.min_free_bytes:
                raise RuntimeError("minimum free disk reserve would be violated")
            partitions = cast(list[dict[str, object]], manifest["partitions"])
            _write_partition(output, config, len(partitions), cast(int, manifest["next_index"]), intended, fault)
            manifest = _reconcile(output, config, manifest)
            _write_manifest(output, manifest, fault)
        return _write_report(output, config, manifest)


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
