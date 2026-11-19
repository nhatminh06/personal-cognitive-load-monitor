from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSESSMENT = ROOT / "docs/course-completion/c16-evidence/assessment.json"


def test_c16_qualification_is_local_digest_bound_and_fail_closed() -> None:
    evidence = json.loads(ASSESSMENT.read_text())
    assert evidence["decision"] == "PARTIAL"
    assert len(evidence["qualified_local_images"]) == 7
    for image in evidence["qualified_local_images"].values():
        assert image["image_id"].startswith("sha256:")
        assert len(image["image_id"]) == 71
        assert image["high"] == image["critical"] == 0
        assert len(image["scan_sha256"]) == len(image["sbom_sha256"]) == 64

    blocked = evidence["blocked_image"]
    assert blocked["high"] > 0 and blocked["critical"] > 0
    assert blocked["remediation_attempts"] == 1
    assert evidence["publication"] == {
        "images_published": False,
        "signatures_available": False,
        "attestations_available": False,
        "live_runtime_qualified": False,
    }


def test_c16_builds_pin_every_base_image_by_digest() -> None:
    dockerfiles = sorted((ROOT / "deploy/c16").glob("Dockerfile.*"))
    assert len(dockerfiles) == 5
    for dockerfile in dockerfiles:
        for line in dockerfile.read_text().splitlines():
            if line.startswith("FROM "):
                assert "@sha256:" in line
