from __future__ import annotations

import subprocess

import pytest

from jobs.internal_job_runner import authorized, command_for, run_job


def test_runner_accepts_only_fixed_job_kinds() -> None:
    assert command_for("dbt") == ("dbt", "build")
    assert command_for("spark")[0] == "/opt/spark/bin/spark-submit"
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
