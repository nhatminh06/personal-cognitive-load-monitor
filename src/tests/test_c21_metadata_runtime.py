from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MLMD_IMAGE = (
    "cogniflow-mlmd@sha256:"
    "d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876"
)
WRITER_IMAGE = (
    "cogniflow-metadata-writer@sha256:"
    "c2a8d2322156040087818323c1e5d1e685dbb63142f52bad263512fb00fa2ae1"
)
MYSQL_IMAGE = (
    "cogniflow/mysql@sha256:"
    "febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6"
)


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / "infra/kfp-local" / name).read_text())


def test_mlmd_image_and_database_credentials_fail_closed() -> None:
    deployment = _load("mlmd.yaml")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert container["image"] == MLMD_IMAGE
    assert container["imagePullPolicy"] == "Never"
    assert "--metadata_source_config_type=mysql" in container["args"]
    assert environment["DBCONFIG_USER"]["valueFrom"]["secretKeyRef"]["name"] == (
        "cogniflow-mysql"
    )
    assert environment["DBCONFIG_PASSWORD"]["valueFrom"]["secretKeyRef"][
        "name"
    ] == "cogniflow-mysql"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["runAsUser"] == 10001


def test_mysql_patch_uses_dedicated_user_and_rejects_empty_password() -> None:
    deployment = _load("mysql.yaml")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert container["image"] == MYSQL_IMAGE
    assert container["imagePullPolicy"] == "Never"
    assert environment["MYSQL_ALLOW_EMPTY_PASSWORD"]["$patch"] == "delete"
    assert environment["MYSQL_USER"]["valueFrom"]["secretKeyRef"] == {
        "name": "cogniflow-mysql",
        "key": "username",
    }
    assert "--mysql-native-password=ON" in container["args"]
    assert container["securityContext"]["runAsUser"] == 27
    assert pod["securityContext"]["fsGroup"] == 27
    assert container["lifecycle"]["postStart"]["exec"]["command"] == [
        "/bin/bash", "/docker-entrypoint-initdb.d/02-grant-kfp-databases.sh",
    ]


def test_overlay_removes_upstream_empty_secret_and_pins_source() -> None:
    overlay = _load("kustomization.yaml")
    removal = _load("remove-upstream-mysql-secret.yaml")

    assert "ref=7dd28116ad652bfb7b6c282e7920be84e6a7634a" in overlay[
        "resources"
    ][0]
    assert removal["$patch"] == "delete"
    assert removal["metadata"]["name"] == "mysql-secret"
    assert "metadata-writer.yaml" in {
        str(item.get("path", "")) for item in overlay["patches"]
    }


def test_overlay_reuses_qualified_controller_identities() -> None:
    expected = {
        "kfp-api.yaml": "sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad",
        "persistence-agent.yaml": "sha256:707c3af5abdb6c57902036916fd0d74d6bb014889a30c19e16574a71c92a68dc",
        "scheduled-workflow.yaml": "sha256:9fa52c2f7e8a6eb62df0e38afec42be1d44cd15ffd85cd3942b2910455d491f3",
        "workflow-controller.yaml": "sha256:c115303d506de611f4d230c1a3f234eb7b1feae153c755a79dad56ebb91b44fd",
        "metadata-envoy.yaml": "sha256:bf7ad93d1c0621f0081e1c2f5be1e96b6955b2615115564837f88b3e95c33126",
    }

    for name, digest in expected.items():
        assert digest in (ROOT / "infra/kfp-local" / name).read_text()


def test_mlmd_build_preserves_upstream_binary_on_supported_non_root_base() -> None:
    dockerfile = (ROOT / "deploy/c21/mlmd/Dockerfile").read_text()

    assert dockerfile.count("@sha256:") == 2
    assert "ubuntu@sha256:73b999393d07" in dockerfile
    assert "COPY --from=upstream" in dockerfile
    assert "USER 10001:10001" in dockerfile


def test_metadata_writer_is_pinned_bounded_and_uses_real_mlmd_service() -> None:
    deployment = _load("metadata-writer.yaml")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert container["image"] == WRITER_IMAGE
    assert container["imagePullPolicy"] == "Never"
    assert environment["METADATA_GRPC_SERVICE_HOST"]["value"] == (
        "metadata-grpc-service"
    )
    assert environment["METADATA_GRPC_SERVICE_PORT"]["value"] == "8080"
    assert container["resources"]["limits"] == {"cpu": "500m", "memory": "512Mi"}
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["runAsUser"] == 65532


def test_metadata_writer_build_uses_checksum_native_source_retrieval() -> None:
    dockerfile = (ROOT / "deploy/c22/metadata-writer/Dockerfile").read_text()

    assert "ADD --checksum=sha256:4b50a172" in dockerfile
    assert "wget" not in dockerfile and "curl" not in dockerfile
    assert "--require-hashes" in dockerfile
    assert "USER 65532:65532" in dockerfile
