"""Read Cloudflare GraphQL CPU buckets and match them to paced synthetic phases."""
import hashlib
import json
import statistics
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
ACCOUNT = "efed917905c163b5f88bb0acbf8d235c"
QUERY = '''query($accountTag:string,$start:string,$end:string){viewer{accounts(filter:{accountTag:$accountTag}){
workersInvocationsAdaptive(limit:1000,filter:{scriptName:"cogniflow-v01",datetime_geq:$start,datetime_leq:$end}){
sum{requests errors subrequests} quantiles{cpuTimeP50 cpuTimeP99} dimensions{datetime status scriptName}}
}}}'''


def moment(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    phases = json.loads((ROOT / "build/cloudflare-ts-live-cpu-workload.json").read_text())["phases"]
    start = moment(phases[0]["start"]) - timedelta(seconds=2)
    end = moment(phases[-1]["end"]) + timedelta(seconds=2)
    token = tomllib.loads(Path("/home/pnmynh/.config/.wrangler/config/default.toml").read_text())["oauth_token"]
    response = httpx.post("https://api.cloudflare.com/client/v4/graphql",
                          headers={"Authorization": "Bearer " + token},
                          json={"query": QUERY, "variables": {"accountTag": ACCOUNT,
                                "start": start.isoformat(), "end": end.isoformat()}}, timeout=30)
    response.raise_for_status()
    data = response.json()
    assert not data.get("errors"), data.get("errors")
    buckets = data["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]
    summary = []
    for phase in phases:
        a, b = moment(phase["start"]).replace(microsecond=0), moment(phase["end"]).replace(microsecond=0)
        selected = [row for row in buckets if a <= moment(row["dimensions"]["datetime"]) <= b]
        values = []
        for row in selected:
            count = row["sum"]["requests"]
            if count == 1:
                values.append(row["quantiles"]["cpuTimeP99"] / 1000)
        values.sort()
        summary.append({"endpoint": phase["endpoint"], "sent": phase["count"],
                        "observed_requests": sum(row["sum"]["requests"] for row in selected),
                        "single_request_cpu_samples": len(values),
                        "errors": sum(row["sum"]["errors"] for row in selected),
                        "multi_request_buckets": sum(row["sum"]["requests"] != 1 for row in selected),
                        "median_ms": round(statistics.median(values), 3) if values else None,
                        "p95_ms": round(values[int(.95 * (len(values) - 1))], 3) if values else None,
                        "max_ms": round(max(values), 3) if values else None})
    artifact = ROOT / "build/cloudflare-ts-live-cpu-telemetry.json"
    artifact.write_text(json.dumps({"source": "Cloudflare GraphQL workersInvocationsAdaptive, microseconds converted to ms",
                                    "summary": summary}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("sha256", hashlib.sha256(artifact.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
