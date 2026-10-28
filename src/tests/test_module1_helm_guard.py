from __future__ import annotations

import hashlib

import pytest

from scripts.module1_helm_guard import validate_existing_release, validate_target


MANIFEST = b"apiVersion: apps/v1\nkind: Deployment\n"
IDENTITY = hashlib.sha256(MANIFEST).hexdigest()


def status(namespace: str = "cogniflow") -> dict:
    return {"name": "cognitive-load-monitor", "namespace": namespace, "version": 7,
            "info": {"status": "deployed"}}


def values(owner: str = "module3-standard", mode: str = "Standard") -> dict:
    return {"deploymentOwner": owner, "kserve": {"deploymentMode": mode}}


def test_new_release_target_requires_exact_context_and_namespace() -> None:
    validate_target("gke_project_region_cluster", "gke_project_region_cluster", "cogniflow")
    with pytest.raises(ValueError, match="context"):
        validate_target("kind-local", "gke_project_region_cluster", "cogniflow")
    with pytest.raises(ValueError, match="namespace"):
        validate_target("gke_project_region_cluster", "gke_project_region_cluster", "other")


def test_existing_module3_release_conflicts_without_separate_authorization() -> None:
    with pytest.raises(ValueError, match="separate replacement authorization"):
        validate_existing_release(
            status(), values(), MANIFEST,
            allow_standard_replacement=False, approved_revision="7", approved_identity=IDENTITY,
        )


def test_existing_pending_release_fails_closed() -> None:
    pending = status()
    pending["info"]["status"] = "pending-upgrade"
    with pytest.raises(ValueError, match="deployed state"):
        validate_existing_release(
            pending, values(), MANIFEST,
            allow_standard_replacement=True, approved_revision="7", approved_identity=IDENTITY,
        )


def test_approved_module3_replacement_requires_exact_revision_and_identity() -> None:
    result = validate_existing_release(
        status(), values(), MANIFEST,
        allow_standard_replacement=True, approved_revision="7", approved_identity=IDENTITY,
    )
    assert result == {
        "release": "cognitive-load-monitor", "namespace": "cogniflow",
        "owner": "module3-standard", "mode": "Standard", "revision": "7", "identity": IDENTITY,
    }
    with pytest.raises(ValueError, match="revision or immutable"):
        validate_existing_release(
            status(), values(), MANIFEST,
            allow_standard_replacement=True, approved_revision="6", approved_identity=IDENTITY,
        )
    with pytest.raises(ValueError, match="revision or immutable"):
        validate_existing_release(
            status(), values(), MANIFEST + b"changed",
            allow_standard_replacement=True, approved_revision="7", approved_identity=IDENTITY,
        )


@pytest.mark.parametrize(
    ("release_status", "release_values", "message"),
    (
        (status("other"), values(), "namespace mismatch"),
        (status(), values("", "Standard"), "ownership"),
        (status(), values("module1-knative", "Standard"), "disagree"),
    ),
)
def test_existing_release_rejects_wrong_namespace_missing_owner_and_mode_mismatch(
    release_status, release_values, message
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_existing_release(
            release_status, release_values, MANIFEST,
            allow_standard_replacement=True, approved_revision="7", approved_identity=IDENTITY,
        )
