"""Fail-closed host and deployment preflight without invoking Docker."""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
from pathlib import Path

MIN_MEMORY_BYTES = 2 * 1024**3
MIN_DISK_BYTES = 4 * 1024**3
DEFERRED_TOKENS = ("spark", "kfp", "kserve")


def unit_state(unit: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", unit], capture_output=True, text=True, check=False
    )
    if result.returncode not in {0, 3}:
        raise RuntimeError(f"cannot verify {unit} state: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def available_memory() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret", type=Path, default=Path("build/mvp/cogniflow_api_key"))
    args = parser.parse_args()

    states = {unit: unit_state(unit) for unit in ("docker.service", "docker.socket", "containerd.service")}
    if any(state != "inactive" for state in states.values()):
        raise RuntimeError(f"runtime units must remain inactive before owner authorization: {states}")
    if available_memory() < MIN_MEMORY_BYTES:
        raise RuntimeError("MVP requires at least 2 GiB available memory")
    if shutil.disk_usage(".").free < MIN_DISK_BYTES:
        raise RuntimeError("MVP requires at least 4 GiB free repository storage")
    if not args.secret.is_file() or not args.secret.read_text(encoding="utf-8").strip():
        raise RuntimeError(f"create a non-empty local secret at {args.secret}")
    if stat.S_IMODE(args.secret.stat().st_mode) & 0o007:
        raise RuntimeError(f"{args.secret} must not be accessible by other users")

    compose = Path("compose.mvp.yml").read_text(encoding="utf-8").lower()
    for token in DEFERRED_TOKENS:
        if token in compose:
            raise RuntimeError(f"deferred component appears in MVP Compose: {token}")
    for required in ("127.0.0.1:18000:8000", 'restart: "no"', "mem_limit: 768m", "cpus: 1.0"):
        if required not in compose:
            raise RuntimeError(f"missing MVP deployment invariant: {required}")

    print(f"PASS: runtime inactive; memory={available_memory()} bytes; disk={shutil.disk_usage('.').free} bytes")
    print("PASS: secret permissions and MVP static deployment invariants")
    print("NOTE: this does not close the offline restart-policy inventory or authorize Docker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
