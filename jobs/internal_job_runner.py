"""Authenticated, fixed-action runner for local Spark and dbt orchestration."""

from __future__ import annotations

import hmac
import json
import os
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COMMANDS = {
    "spark": (
        "/opt/spark/bin/spark-submit",
        "--packages",
        "io.delta:delta-spark_2.12:3.3.2,org.apache.hadoop:hadoop-aws:3.3.4",
        "jobs/bronze_to_silver.py",
    ),
    "dbt": ("dbt", "build"),
}
WORKING_DIRS = {"spark": "/opt/cogniflow", "dbt": "/analytics"}
_job_lock = threading.Lock()


def command_for(kind: str) -> tuple[str, ...]:
    """Return one of the two compile-time allowlisted commands."""
    try:
        return COMMANDS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported job kind: {kind}") from exc


def authorized(header: str | None, token: str) -> bool:
    supplied = header[7:] if header and header.startswith("Bearer ") else ""
    return bool(token) and hmac.compare_digest(supplied, token)


def run_job(kind: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command_for(kind), cwd=WORKING_DIRS[kind], capture_output=True,
        check=False, text=True, timeout=timeout,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "CogniFlowJobRunner/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._reply(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        self._reply(HTTPStatus.OK, {"status": "healthy"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            self._reply(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        token = os.environ.get("JOB_RUNNER_TOKEN", "")
        if not authorized(self.headers.get("Authorization"), token):
            self._reply(HTTPStatus.UNAUTHORIZED, {"detail": "Invalid runner token"})
            return
        length = self.headers.get("Content-Length", "0")
        if not length.isdigit() or int(length) > 2:
            self._reply(HTTPStatus.BAD_REQUEST, {"detail": "Request body must be empty"})
            return
        if int(length):
            self.rfile.read(int(length))
        if not _job_lock.acquire(blocking=False):
            self._reply(HTTPStatus.CONFLICT, {"detail": "A job is already running"})
            return
        try:
            result = run_job(os.environ["JOB_KIND"], int(os.getenv("JOB_TIMEOUT_SECONDS", "1800")))
        except (KeyError, ValueError):
            self._reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": "Runner is misconfigured"})
        except subprocess.TimeoutExpired:
            self._reply(HTTPStatus.GATEWAY_TIMEOUT, {"detail": "Job timed out"})
        else:
            output = (result.stdout + result.stderr)[-4000:]
            status = HTTPStatus.OK if result.returncode == 0 else HTTPStatus.BAD_GATEWAY
            self._reply(status, {"exit_code": result.returncode, "output": output})
        finally:
            _job_lock.release()

    def log_message(self, format: str, *args: object) -> None:
        print(f"job-runner: {format % args}", flush=True)

    def _reply(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    command_for(os.environ.get("JOB_KIND", ""))
    if not os.environ.get("JOB_RUNNER_TOKEN", "").strip():
        raise RuntimeError("JOB_RUNNER_TOKEN must be configured")
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()


if __name__ == "__main__":
    main()
