from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[2]
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def test_c59_packet_fails_closed_until_publication_evidence_exists() -> None:
    packet = json.loads(
        (ROOT / "deploy/releases/c59-local-artifacts.json").read_text()
    )
    assert packet["status"] == "BLOCKED"
    assert packet["registry"] == {
        "location": "us-central1",
        "project_id": None,
        "repository": "cogniflow-images",
    }
    assert set(packet["artifacts"]) == {
        "cognitive-load-api", "cogniflow-deploy-runner", "cogniflow-kserve",
    }
    for name, artifact in packet["artifacts"].items():
        assert artifact["planned_repository"] == name
        assert DIGEST.fullmatch(artifact["local_index_digest"])
        assert artifact["remote_reference"] is None
        runtime = artifact["local_runtime_manifest_digest"]
        assert runtime is None or DIGEST.fullmatch(runtime)
    assert packet["artifacts"]["cogniflow-deploy-runner"]["raw_evidence_complete"] is True
    assert packet["artifacts"]["cognitive-load-api"]["raw_evidence_complete"] is False
    assert packet["artifacts"]["cogniflow-kserve"]["raw_evidence_complete"] is False
