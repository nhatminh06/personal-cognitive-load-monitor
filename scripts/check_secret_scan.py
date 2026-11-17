"""Fail closed when a Gitleaks JSON report is missing, malformed, or nonempty."""

import json
import sys
from pathlib import Path


def verify(paths: list[Path]) -> None:
    if not paths:
        raise ValueError("at least one scan report is required")
    for path in paths:
        findings = json.loads(path.read_text())
        if not isinstance(findings, list):
            raise ValueError(f"invalid scan report: {path.name}")
        if findings:
            raise ValueError(f"{path.name}: {len(findings)} redacted finding(s)")


if __name__ == "__main__":
    try:
        verify([Path(arg) for arg in sys.argv[1:]])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"secret scan gate failed: {exc}") from exc
