"""Offline checks for Eventing dependency lock structure and pip enforcement."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import subprocess
import tomllib
import venv
import zipfile
from pathlib import Path

import pytest
from packaging.utils import canonicalize_name

from scripts.eventing_lock import HASH, LockError, _logical_lines, inspect_lock

ROOT = Path(__file__).resolve().parents[2]
IMAGES = (
    (
        "event-consumer",
        ROOT / "requirements-event-consumer.txt",
        ROOT / "requirements-event-consumer.lock",
        ROOT / "Dockerfile.event-consumer",
    ),
    (
        "anomaly-detector",
        ROOT / "requirements-anomaly-detector.txt",
        ROOT / "requirements-anomaly-detector.lock",
        ROOT / "Dockerfile.anomaly-detector",
    ),
)
DIRECT = {"fastapi", "prometheus-client", "uvicorn"}


def _locked_names(lock: Path) -> set[str]:
    names = set()
    for line in _logical_lines(lock.read_text()):
        names.add(canonicalize_name(HASH.sub("", line).split(" #", 1)[0].split("==", 1)[0]))
    return names


def _locked_versions(lock: Path) -> dict[str, str]:
    return {
        canonicalize_name(line.split("==", 1)[0]): line.split("==", 1)[1].split()[0]
        for line in _logical_lines(lock.read_text())
    }


def _wheel(directory: Path, name: str, dependency: str | None = None) -> Path:
    wheel = directory / f"{name}-1.0.0-py3-none-any.whl"
    dist_info = f"{name}-1.0.0.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0.0\n"
    if dependency:
        metadata += f"Requires-Dist: {dependency}\n"
    members = {
        f"{name}/__init__.py": b"__version__ = '1.0.0'\n",
        f"{dist_info}/METADATA": metadata.encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    rows = []
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, payload in members.items():
            archive.writestr(path, payload)
            digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
            rows.append((path, f"sha256={digest}", str(len(payload))))
        record = f"{dist_info}/RECORD"
        rows.append((record, "", ""))
        output = io.StringIO()
        csv.writer(output, lineterminator="\n").writerows(rows)
        archive.writestr(record, output.getvalue())
    return wheel


def _install(
    python: Path, wheels: Path, lock: Path, target: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-index",
            "--only-binary=:all:",
            "--require-hashes",
            "--no-cache-dir",
            "--find-links",
            str(wheels),
            "--target",
            str(target),
            "-r",
            str(lock),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(("name", "source", "lock", "dockerfile"), IMAGES)
def test_real_eventing_lock_is_complete_and_enforced(
    name: str, source: Path, lock: Path, dockerfile: Path
) -> None:
    distribution_count, hash_count = inspect_lock(source, lock)
    locked = _locked_names(lock)
    assert DIRECT <= locked
    assert distribution_count > len(DIRECT), "transitive dependencies must be locked"
    assert hash_count >= distribution_count
    project_versions = {
        canonicalize_name(package["name"]): package["version"]
        for package in tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    }
    assert _locked_versions(lock) == {package: project_versions[package] for package in locked}
    content = dockerfile.read_text()
    assert lock.name in content
    assert "--require-hashes" in content
    assert "--only-binary=:all:" in content
    assert source.name not in content


def test_lock_verifier_rejects_missing_hash_and_unpinned_requirement(tmp_path: Path) -> None:
    source = tmp_path / "requirements.txt"
    lock = tmp_path / "requirements.lock"
    source.write_text("demo==1.0.0\n")
    for invalid in ("demo==1.0.0\n", f"demo>=1 --hash=sha256:{'a' * 64}\n"):
        lock.write_text(invalid)
        with pytest.raises(LockError):
            inspect_lock(source, lock)


def test_pip_hash_gate_accepts_valid_lock_and_rejects_corruption_and_missing_transitive(
    tmp_path: Path,
) -> None:
    pip_environment = tmp_path / "pip-environment"
    venv.EnvBuilder(with_pip=True).create(pip_environment)
    python = pip_environment / "bin/python"
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    dependency = _wheel(wheels, "fixturedep")
    main = _wheel(wheels, "fixturemain", "fixturedep==1.0.0")
    main_hash = hashlib.sha256(main.read_bytes()).hexdigest()
    dependency_hash = hashlib.sha256(dependency.read_bytes()).hexdigest()
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        f"fixturemain==1.0.0 --hash=sha256:{main_hash}\nfixturedep==1.0.0 --hash=sha256:{dependency_hash}\n"
    )
    assert _install(python, wheels, lock, tmp_path / "valid").returncode == 0
    lock.write_text(
        f"fixturemain==1.0.0 --hash=sha256:{'0' * 64}\nfixturedep==1.0.0 --hash=sha256:{dependency_hash}\n"
    )
    assert _install(python, wheels, lock, tmp_path / "corrupt").returncode != 0
    lock.write_text(f"fixturemain==1.0.0 --hash=sha256:{main_hash}\n")
    assert _install(python, wheels, lock, tmp_path / "missing").returncode != 0
