from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.generate_module2_benchmark as benchmark
from scripts.generate_module2_benchmark import Config, directory_lock, generate, sha256


class Crash(RuntimeError):
    pass


def config(**overrides: int) -> Config:
    return Config(overrides.get("target_bytes", 12_345), overrides.get("max_bytes", 20_000), overrides.get("partition_bytes", 5_000), overrides.get("min_free_bytes", 0), overrides.get("seed", 42), "2026-01-01T00:00:00+00:00")


def run(path: Path, current: Config, *, resume: bool = False, fault=None):
    return generate(path, current, execute=True, allow_over_100gb=False, resume=resume, fault=fault)


def crash_at(stage: str):
    def inject(observed: str) -> None:
        if observed == stage:
            raise Crash(stage)

    return inject


def assert_complete(path: Path, current: Config) -> None:
    report = json.loads((path / "benchmark-report.json").read_text())
    manifest = json.loads((path / "manifest.json").read_text())
    identifiers = []
    physical_bytes = 0
    rows = 0
    for item in manifest["partitions"]:
        partition = path / item["file"]
        physical_bytes += partition.stat().st_size
        rows += item["rows"]
        assert sha256(partition) == item["sha256"]
        identifiers.extend(json.loads(line)["event_id"] for line in partition.read_text().splitlines())
    assert physical_bytes == current.target_bytes == manifest["committed_bytes"]
    assert sum(item["bytes"] for item in manifest["partitions"]) == physical_bytes
    assert rows == manifest["committed_rows"] == manifest["next_index"]
    assert len(identifiers) == len(set(identifiers)) == report["unique_event_ids"]
    assert report["actual_bytes"] == physical_bytes
    assert report["rows"] == rows
    assert report["next_index"] == rows


def test_benchmark_generator_writes_exact_partitioned_evidence(tmp_path: Path) -> None:
    current = config()
    run(tmp_path, current)
    assert_complete(tmp_path, current)
    assert len(json.loads((tmp_path / "manifest.json").read_text())["partitions"]) == 3


def test_normal_generation_verifies_each_partition_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    verified = []
    original = benchmark._verify_partition

    def track(path: Path, current: Config, start_index: int):
        verified.append(path.name)
        return original(path, current, start_index)

    monkeypatch.setattr(benchmark, "_verify_partition", track)
    run(tmp_path, config(target_bytes=40_000, max_bytes=40_000))
    assert verified == [f"part-{number:06d}.jsonl" for number in range(8)]


def test_resume_scans_every_committed_partition_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = config(target_bytes=40_000, max_bytes=40_000)
    run(tmp_path, current)
    scanned_bytes = 0
    original = benchmark._verify_partition

    def track(path: Path, resumed: Config, start_index: int):
        nonlocal scanned_bytes
        scanned_bytes += path.stat().st_size
        return original(path, resumed, start_index)

    monkeypatch.setattr(benchmark, "_verify_partition", track)
    run(tmp_path, current, resume=True)
    assert scanned_bytes == current.target_bytes


@pytest.mark.parametrize("stage", ["after_partition_temp_fsync", "after_partition_publish", "after_manifest_temp_fsync", "after_manifest_replace"])
def test_fault_injection_recovers_and_reconciles(tmp_path: Path, stage: str) -> None:
    current = config()
    with pytest.raises(Crash, match=stage):
        run(tmp_path, current, fault=crash_at(stage))
    run(tmp_path, current, resume=True)
    assert_complete(tmp_path, current)
    assert not list(tmp_path.glob("*.tmp"))


def test_resume_repairs_untrusted_manifest_counters(tmp_path: Path) -> None:
    current = config()
    run(tmp_path, current)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update({"committed_bytes": 1, "committed_rows": 999, "next_index": 999})
    manifest_path.write_text(json.dumps(manifest))
    run(tmp_path, current, resume=True)
    assert_complete(tmp_path, current)


def test_resume_rejects_missing_and_tampered_partitions(tmp_path: Path) -> None:
    current = config()
    run(tmp_path, current)
    first = tmp_path / "part-000000.jsonl"
    original = first.read_bytes()
    first.unlink()
    with pytest.raises(ValueError, match="missing"):
        run(tmp_path, current, resume=True)
    first.write_bytes(original[:-1] + b"x")
    with pytest.raises(ValueError, match="mismatch"):
        run(tmp_path, current, resume=True)


def test_interrupted_manifest_write_recovers(tmp_path: Path) -> None:
    current = config()
    with pytest.raises(Crash, match="after_manifest_temp_fsync"):
        run(tmp_path, current, fault=crash_at("after_manifest_temp_fsync"))
    run(tmp_path, current, resume=True)
    assert_complete(tmp_path, current)


def test_incomplete_manifest_temp_is_discarded(tmp_path: Path) -> None:
    current = config()
    run(tmp_path, current)
    (tmp_path / "manifest.json.tmp").write_text('{"partitions":')
    run(tmp_path, current, resume=True)
    assert_complete(tmp_path, current)
    assert not (tmp_path / "manifest.json.tmp").exists()


def test_concurrent_generator_is_rejected(tmp_path: Path) -> None:
    current = config()
    with directory_lock(tmp_path):
        with pytest.raises(RuntimeError, match="another benchmark generator"):
            run(tmp_path, current)


def test_completed_partition_is_never_overwritten(tmp_path: Path) -> None:
    current = config()
    partition = tmp_path / "part-000000.jsonl"
    partition.write_text("preserve")
    before = partition.read_bytes()
    with pytest.raises(ValueError, match="output directory must be empty"):
        run(tmp_path, current)
    assert partition.read_bytes() == before


def test_benchmark_generator_requires_explicit_large_run_authorization(tmp_path: Path) -> None:
    large = config(target_bytes=100_000_000_001, max_bytes=100_000_000_001)
    with pytest.raises(ValueError, match="allow-over-100gb"):
        generate(tmp_path, large, execute=True, allow_over_100gb=False, resume=False)
    with pytest.raises(ValueError, match="explicit --execute"):
        generate(tmp_path, config(), execute=False, allow_over_100gb=False, resume=False)
