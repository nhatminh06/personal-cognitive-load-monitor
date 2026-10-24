"""Export the committed Module II event JSON Schema."""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cogniflow_data.events import SessionEvent  # noqa: E402


def main() -> None:
    destination = Path("docs/module2/schemas/session-event-v1.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(SessionEvent.model_json_schema(), indent=2) + "\n")


if __name__ == "__main__":
    main()
