"""Export deterministic JSON Schemas for focus-session contracts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cogniflow_contracts import CONTRACT_MODELS, contract_schema_filename  # noqa: E402


def export_schemas(destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for topic, model in CONTRACT_MODELS.items():
        path = destination / contract_schema_filename(topic)
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":
    export_schemas(Path("docs/focus-session/schemas"))
