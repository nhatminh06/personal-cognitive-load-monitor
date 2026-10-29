"""Export an immutable owner-scoped multimodal dataset or synthetic fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from cogniflow_data.multimodal import write_dataset_bundle
from cogniflow_sessions import FocusSessionRepository


def _git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument("--snapshot", type=Path)
    parser.add_argument("--snapshot-cutoff", type=datetime.fromisoformat)
    parser.add_argument("--authorize-private-data", action="store_true")
    parser.add_argument("--allow-synthetic-fixture", action="store_true")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--git-revision", default=None)
    args = parser.parse_args()

    if args.database:
        if not args.authorize_private_data or args.snapshot_cutoff is None:
            parser.error("database export requires --authorize-private-data and --snapshot-cutoff")
        api_key = os.getenv("COGNIFLOW_EXPERIMENT_API_KEY")
        if not api_key or not api_key.strip():
            parser.error("set COGNIFLOW_EXPERIMENT_API_KEY for owner-scoped export")
        owner = hashlib.sha256(api_key.encode()).hexdigest()
        snapshot = FocusSessionRepository(args.database).experiment_snapshot(owner, args.snapshot_cutoff)
        data_provenance = "local_user_sessions"
    else:
        if not args.allow_synthetic_fixture:
            parser.error("snapshot files require --allow-synthetic-fixture")
        snapshot = json.loads(args.snapshot.read_text())
        if snapshot.get("data_provenance") != "synthetic_pipeline_fixture":
            parser.error("only explicitly marked synthetic fixture snapshots are accepted")
        data_provenance = "synthetic_pipeline_fixture"

    manifest, splits = write_dataset_bundle(
        snapshot, args.dataset, args.manifest, args.splits,
        git_revision=args.git_revision or _git_revision(), random_seed=args.random_seed,
        data_provenance=data_provenance,
    )
    print(json.dumps({"row_count": manifest["row_count"], "split_status": splits["status"]}))


if __name__ == "__main__":
    main()
