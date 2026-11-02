#!/usr/bin/env python3
"""Generate and verify hash-pinned Eventing requirements."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

HASH = re.compile(r"(?<!\S)--hash=sha256:([0-9a-fA-F]{64})(?!\S)")


class LockError(ValueError):
    """A lock fails structural policy validation."""


def _logical_lines(content: str) -> list[str]:
    joined = content.replace("\\\r\n", " ").replace("\\\n", " ")
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _requirement(value: str, label: str) -> Requirement:
    try:
        requirement = Requirement(value)
    except InvalidRequirement as exc:
        raise LockError(f"Invalid {label}: {value!r}") from exc
    if requirement.url is not None:
        raise LockError(f"URLs, VCS, and local paths are forbidden in {label}: {value!r}")
    return requirement


def inspect_lock(source: Path, lock: Path) -> tuple[int, int]:
    if not source.is_file() or not lock.is_file():
        raise LockError("Both source and lock must exist")

    direct: set[str] = set()
    for item in _logical_lines(source.read_text(encoding="utf-8")):
        if item.startswith(("-", ".", "/")):
            raise LockError(f"Unsupported source directive or path: {item!r}")
        direct.add(canonicalize_name(_requirement(item, "source requirement").name))
    if not direct:
        raise LockError("Empty source requirements file")

    versions: dict[str, str] = {}
    hash_count = 0
    for item in _logical_lines(lock.read_text(encoding="utf-8")):
        if item.startswith(("-", ".", "/")):
            raise LockError(f"Unsupported lock directive or path: {item!r}")
        hashes = HASH.findall(item)
        if not hashes:
            raise LockError(f"Lock entry has no SHA-256 hash: {item!r}")
        value = HASH.sub("", item).split(" #", 1)[0].strip()
        if " --" in value or value.startswith("-"):
            raise LockError(f"Unsupported lock option: {item!r}")
        requirement = _requirement(value, "lock requirement")
        pins = [
            specifier.version
            for specifier in requirement.specifier
            if specifier.operator == "==" and not specifier.version.endswith(".*")
        ]
        if len(requirement.specifier) != 1 or len(pins) != 1:
            raise LockError(f"Each lock entry must have one exact ==version: {item!r}")
        name = canonicalize_name(requirement.name)
        if name in versions:
            raise LockError(f"Repeated requirement {name!r}; marker forks require review")
        versions[name] = pins[0]
        hash_count += len(hashes)

    missing = direct - set(versions)
    if missing:
        raise LockError(f"Direct requirements missing from lock: {', '.join(sorted(missing))}")
    return len(versions), hash_count


def generate(
    source: Path,
    lock: Path,
    python_version: str,
    platform: str,
    constraints: Path | None,
) -> None:
    if not source.is_file():
        raise LockError(f"Requirements source does not exist: {source}")
    if source.resolve() == lock.resolve():
        raise LockError("Cannot overwrite the source requirements")
    if lock.exists():
        raise LockError(f"Lock exists: {lock}; remove it only for an explicit update")
    command = [
        "uv",
        "pip",
        "compile",
        str(source),
        "--python-version",
        python_version,
        "--python-platform",
        platform,
        "--only-binary",
        ":all:",
        "--generate-hashes",
        "--no-annotate",
        "--no-header",
        "--output-file",
        str(lock),
    ]
    if constraints is not None:
        command.extend(("--constraint", str(constraints)))
    try:
        subprocess.run(command, check=True)
        count, hashes = inspect_lock(source, lock)
    except Exception:
        lock.unlink(missing_ok=True)
        raise
    print(f"Generated {lock}: {count} pinned distributions, {hashes} SHA-256 hashes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("generate", "verify"):
        command = actions.add_parser(action)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--lock", type=Path, required=True)
        if action == "generate":
            command.add_argument("--python-version", required=True)
            command.add_argument("--constraints", type=Path)
            command.add_argument(
                "--platform",
                required=True,
                choices=["x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu"],
            )
    args = parser.parse_args()
    try:
        if args.action == "generate":
            generate(args.source, args.lock, args.python_version, args.platform, args.constraints)
        else:
            count, hashes = inspect_lock(args.source, args.lock)
            print(f"PASS {args.lock}: {count} exact pins, {hashes} SHA-256 hashes")
    except (OSError, LockError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
