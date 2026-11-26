"""Match synthetic CF-Ray IDs to Cloudflare invocation CPU without retaining raw logs."""
import hashlib
import json
import statistics
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
TOKEN = Path.home() / ".config/cogniflow/observability-token"
ENDPOINT = ("https://api.cloudflare.com/client/v4/accounts/"
            "efed917905c163b5f88bb0acbf8d235c/workers/observability/telemetry/query")


def millis(value):
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def ray(value):
    return value.split("-", 1)[0].lower() if isinstance(value, str) else None


def fetch_events(start, end):
    body = {"queryId": "cogniflow-invocation-cpu-qualification",
            "timeframe": {"from": start, "to": end}, "view": "events", "limit": 2000,
            "parameters": {"datasets": ["cloudflare-workers"], "filterCombination": "and",
                           "filters": [{"key": "$metadata.service", "operation": "eq", "type": "string",
                                        "value": "cogniflow-v01"}]}}
    token = TOKEN.read_text().strip()
    response = httpx.post(ENDPOINT, headers={"Authorization": "Bearer " + token}, json=body, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("success") is not True or data.get("errors") or data.get("result", {}).get("run", {}).get("status") != "COMPLETED":
        raise RuntimeError("Cloudflare telemetry query was not completed successfully")
    events = data["result"].get("events") or {}
    rows = events.get("events") or []
    if not isinstance(rows, list) or events.get("count", 0) > len(rows):
        raise RuntimeError("Cloudflare telemetry result requires pagination; qualification is unverified")
    return rows


def summarize(samples, rows):
    by_ray = {}
    for row in rows:
        meta, worker = row.get("$metadata") or {}, row.get("$workers") or {}
        key = ray(meta.get("rayId"))
        if key and worker.get("cpuTimeMs") is not None:
            record = {"request_id": meta.get("requestId"), "cpu_ms": float(worker["cpuTimeMs"]),
                      "outcome": worker.get("outcome"),
                      "response_status": ((worker.get("event") or {}).get("response") or {}).get("status")}
            if key in by_ray and by_ray[key]["request_id"] != record["request_id"]:
                raise RuntimeError("A Ray ID mapped to multiple invocations")
            by_ray[key] = record
    grouped = defaultdict(list)
    seen = set()
    for sample in samples:
        key = ray(sample.get("ray_id"))
        if key in seen and key is not None:
            raise RuntimeError("Duplicate response Ray ID in synthetic workload")
        seen.add(key)
        grouped[sample["endpoint"]].append((sample, by_ray.get(key)))
    summary = []
    for endpoint, pairs in grouped.items():
        values = sorted(record["cpu_ms"] for _, record in pairs if record)
        missing = [sample["index"] for sample, record in pairs if record is None]
        failures = [{"index": sample["index"], "http_status": sample["status"],
                     "outcome": record["outcome"] if record else None}
                    for sample, record in pairs
                    if sample["status"] >= 500 or (record and record["outcome"] not in ("ok", "success"))]
        summary.append({"endpoint": endpoint, "sent": len(pairs), "matched": len(values),
                        "missing_indexes": missing, "failures": failures,
                        "median_ms": round(statistics.median(values), 3) if values else None,
                        "p95_ms": round(values[int(.95 * (len(values) - 1))], 3) if values else None,
                        "max_ms": round(max(values), 3) if values else None,
                        "cpu_over_10ms": sum(value > 10 for value in values)})
    return summary


def main():
    workload = json.loads((ROOT / "build/cloudflare-ts-live-cpu-workload.json").read_text())
    samples = workload["samples"]
    start = millis(workload["phases"][0]["start"]) - 10_000
    end = millis(workload["phases"][-1]["end"]) + 10_000
    for attempt in range(5):
        summary = summarize(samples, fetch_events(start, end))
        if all(item["matched"] == item["sent"] for item in summary):
            break
        if attempt < 4:
            time.sleep(20)
    artifact = ROOT / "build/cloudflare-ts-live-invocation-cpu.json"
    artifact.write_text(json.dumps({"source": "Cloudflare Workers Observability invocation logs",
                                    "summary": summary}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("sha256", hashlib.sha256(artifact.read_bytes()).hexdigest())
    ready = all(item["matched"] >= 30 and item["matched"] / item["sent"] >= .95
                and not item["failures"] and item["max_ms"] < 10 and item["p95_ms"] < 8
                for item in summary)
    print("CPU_GATE", "PASS" if ready else "UNVERIFIED_OR_FAILED")
    if not ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
