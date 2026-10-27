from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_module2_benchmark import Config, generate, sha256


def config(**overrides: int) -> Config:
    return Config(
        target_bytes=overrides.get("target_bytes", 12_345),
        max_bytes=overrides.get("max_bytes", 20_000),
        partition_bytes=overrides.get("partition_bytes", 5_000),
        min_free_bytes=overrides.get("min_free_bytes", 0),
        seed=overrides.get("seed", 42),
        start="2026-01-01T00:00:00+00:00",
    )


def test_benchmark_generator_writes_exact_partitioned_evidence(tmp_path: Path) -> None:
    report = generate(tmp_path, config(), execute=True, allow_over_100gb=False, resume=False)
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert report["actual_bytes"] == 12_345
    assert sum(item["bytes"] for item in manifest["partitions"]) == 12_345
    assert len(manifest["partitions"]) == 3
    for item in manifest["partitions"]:
        path = tmp_path / item["file"]
        assert path.stat().st_size == item["bytes"]
        assert sha256(path) == item["sha256"]
        for line in path.read_text().splitlines():
            json.loads(line)
    assert (tmp_path / "benchmark-report.json").is_file()
    assert (tmp_path / "benchmark-summary.md").is_file()


def test_benchmark_generator_requires_explicit_large_run_authorization(tmp_path: Path) -> None:
    large = config(target_bytes=100_000_000_001, max_bytes=100_000_000_001)
    with pytest.raises(ValueError, match="allow-over-100gb"):
        generate(tmp_path, large, execute=True, allow_over_100gb=False, resume=False)
    with pytest.raises(ValueError, match="explicit --execute"):
        generate(tmp_path, config(), execute=False, allow_over_100gb=False, resume=False)


def test_benchmark_resume_rejects_tampered_partition(tmp_path: Path) -> None:
    current = config()
    generate(tmp_path, current, execute=True, allow_over_100gb=False, resume=False)
    (tmp_path / "part-000000.jsonl").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="integrity check failed"):
        generate(tmp_path, current, execute=True, allow_over_100gb=False, resume=True)


def test_benchmark_rejects_nonempty_output_without_resume(tmp_path: Path) -> None:
    (tmp_path / "existing").write_text("preserve")
    with pytest.raises(ValueError, match="must be empty"):
        generate(tmp_path, config(), execute=True, allow_over_100gb=False, resume=False)
