from __future__ import annotations

import subprocess
import builtins

import pytest

from jobs.internal_job_runner import Handler, _job_lock, authorized, command_for, main, run_job, verify_spark_ivy


def test_runner_accepts_only_fixed_job_kinds() -> None:
    assert command_for("dbt") == ("dbt", "build")
    assert command_for("spark")[0] == "/opt/spark/bin/spark-submit"
    assert "--packages" not in command_for("spark")
    assert command_for("spark")[1] == "--jars"
    with pytest.raises(ValueError, match="Unsupported job kind"):
        command_for("shell")


def test_runner_authentication_is_fail_closed() -> None:
    assert authorized("Bearer secret", "secret")
    assert not authorized(None, "secret")
    assert not authorized("Bearer wrong", "secret")
    assert not authorized("Basic secret", "secret")
    assert not authorized("Bearer secret", "")


def test_runner_uses_allowlisted_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[str, ...], str, int]] = []

    def fake_run(command, *, cwd, capture_output, check, text, timeout):
        calls.append((command, cwd, timeout))
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_job("dbt", 30).returncode == 0
    assert calls == [(('dbt', 'build'), '/analytics', 30)]


def test_blocked_spark_cannot_start_or_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_KIND", "spark")
    monkeypatch.setenv("JOB_RUNNER_TOKEN", "secret")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Spark executed"))
    monkeypatch.setattr("jobs.internal_job_runner.ThreadingHTTPServer", lambda *args: pytest.fail("Server bound"))
    with pytest.raises(RuntimeError, match="security blocked"):
        main()
    with pytest.raises(RuntimeError, match="security blocked"):
        run_job("spark", 30)


@pytest.mark.parametrize("header,status", [("Bearer secret", 502), ("Bearer wrong", 401), (None, 401)])
def test_spark_validation_never_imports_or_executes(monkeypatch: pytest.MonkeyPatch, header: str | None, status: int) -> None:
    monkeypatch.setenv("JOB_KIND", "spark")
    monkeypatch.setenv("JOB_RUNNER_TOKEN", "secret")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Subprocess started"))
    original_import = builtins.__import__

    def no_spark_import(name, *args, **kwargs):
        if name == "bronze_to_silver" or name.startswith(("pyspark", "delta")):
            pytest.fail(f"Spark module imported: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_spark_import)
    handler = object.__new__(Handler)
    handler.path = "/validate"
    handler.headers = {"Authorization": header} if header else {}
    replies = []
    handler._reply = lambda code, payload: replies.append((code, payload))
    handler.do_POST()
    assert replies[0][0] == status
    assert not _job_lock.locked()


def test_spark_ivy_manifest_is_enforced(tmp_path) -> None:
    cache = tmp_path / "ivy"
    artifact = cache / "jars" / "approved.jar"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"approved")
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(
        "2687f86ed6784b8a5fca36e6c468e12aa44dc3c7e8137e3160d1a95079bdcd02  jars/approved.jar\n"
    )

    verify_spark_ivy(manifest, cache)
    artifact.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="Unverified Spark dependency"):
        verify_spark_ivy(manifest, cache)
    artifact.unlink()
    with pytest.raises(RuntimeError, match="Unverified Spark dependency"):
        verify_spark_ivy(manifest, cache)
