"""Immutable local focus-session datasets and leakage-safe multimodal experiments."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import resource
import statistics
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

import joblib
import pandas as pd
import skops.io
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from cogniflow_contracts import (
    BehavioralActivityEvent,
    CvFeatureWindowEvent,
    EffortLabelEvent,
    SessionLifecycleEvent,
    effort_band,
    validate_label_history,
)

DATASET_SCHEMA_VERSION: Literal["1.0"] = "1.0"
TARGET_VERSION = "self_reported_effort.v1"
BEHAVIORAL_FEATURES = (
    "active_seconds",
    "idle_seconds",
    "keyboard_event_count",
    "pointer_event_count",
    "application_switch_count",
    "build_count",
    "test_count",
)
CV_FEATURES = (
    "face_presence_ratio",
    "gaze_away_ratio",
    "blink_rate_per_minute",
    "head_pose_variance",
    "frame_drop_ratio",
)
MULTIMODAL_FEATURES = (*BEHAVIORAL_FEATURES, *CV_FEATURES, "cv_available")
MINIMUM_ROWS = 90
SELECTION_MAE_MARGIN = 0.25
SELECTION_F1_TOLERANCE = 0.02
BANDS = ("LOW", "MEDIUM", "HIGH")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be UTC")
    return value.astimezone(UTC)


class MultimodalDatasetRow(StrictModel):
    dataset_schema_version: Literal["1.0"] = DATASET_SCHEMA_VERSION
    session_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    subject_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    session_kind: Literal["programming", "study"]
    window_id: UUID
    window_start: datetime
    window_end: datetime
    feature_cutoff: datetime
    dataset_snapshot_cutoff: datetime
    behavioral_event_id: UUID
    cv_event_id: UUID | None = None
    label_event_id: UUID
    active_seconds: float = Field(ge=0, le=300, allow_inf_nan=False)
    idle_seconds: float = Field(ge=0, le=300, allow_inf_nan=False)
    keyboard_event_count: int = Field(ge=0)
    pointer_event_count: int = Field(ge=0)
    application_switch_count: int = Field(ge=0)
    build_count: int | None = Field(default=None, ge=0)
    test_count: int | None = Field(default=None, ge=0)
    face_presence_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    gaze_away_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    blink_rate_per_minute: float | None = Field(default=None, ge=0, le=300, allow_inf_nan=False)
    head_pose_variance: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    frame_drop_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    cv_available: Literal[0, 1]
    self_reported_effort: int = Field(ge=1, le=7)

    @field_validator("window_start", "window_end", "feature_cutoff", "dataset_snapshot_cutoff")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def timing_and_missingness(self) -> Self:
        if self.window_end - self.window_start != timedelta(minutes=5):
            raise ValueError("dataset windows must be exactly five minutes")
        if self.feature_cutoff != self.window_end:
            raise ValueError("feature_cutoff must equal window_end")
        if self.dataset_snapshot_cutoff < self.feature_cutoff:
            raise ValueError("dataset snapshot cannot precede feature cutoff")
        cv_values = tuple(getattr(self, name) for name in CV_FEATURES)
        if self.cv_available and (self.cv_event_id is None or any(value is None for value in cv_values)):
            raise ValueError("available CV requires a source event and complete features")
        if not self.cv_available and any(value is not None for value in cv_values):
            raise ValueError("missing CV features must remain null")
        return self


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _snapshot_digest(snapshot: dict[str, Any]) -> str:
    normalized = dict(snapshot)
    for name, identity in (
        ("sessions", "session_id"), ("windows", "window_id"),
        ("lifecycle", "event_id"), ("activity", "event_id"),
        ("cv", "event_id"), ("labels", "event_id"),
    ):
        normalized[name] = sorted(snapshot.get(name, []), key=lambda item: str(item[identity]))
    return sha256_bytes(_canonical(normalized))


def _pseudonym(kind: str, value: str) -> str:
    return sha256_bytes(f"cogniflow:{kind}:v1:{value}".encode())


def _unique_by_window(events: list[Any], name: str) -> dict[UUID, Any]:
    result: dict[UUID, Any] = {}
    for event in events:
        previous = result.get(event.window_id)
        if previous is not None and previous != event:
            raise ValueError(f"conflicting {name} events for window {event.window_id}")
        if previous is not None:
            raise ValueError(f"duplicate {name} event for window {event.window_id}")
        result[event.window_id] = event
    return result


def build_dataset_rows(snapshot: dict[str, Any]) -> tuple[list[MultimodalDatasetRow], dict[str, Any]]:
    """Join validated SQLite aggregate events at one immutable snapshot cutoff."""

    cutoff = _utc(datetime.fromisoformat(snapshot["snapshot_cutoff"]))
    sessions = {item["session_id"]: item for item in snapshot.get("sessions", [])}
    if len(sessions) != len(snapshot.get("sessions", [])):
        raise ValueError("duplicate session metadata")
    if any(item.get("state") == "session.cancelled" for item in sessions.values()):
        raise ValueError("cancelled sessions cannot enter an experiment snapshot")

    lifecycle = [SessionLifecycleEvent.model_validate(item) for item in snapshot.get("lifecycle", [])]
    activity = [BehavioralActivityEvent.model_validate(item) for item in snapshot.get("activity", [])]
    cv_events = [CvFeatureWindowEvent.model_validate(item) for item in snapshot.get("cv", [])]
    labels = [EffortLabelEvent.model_validate(item) for item in snapshot.get("labels", [])]
    for event in (*lifecycle, *activity, *cv_events, *labels):
        if event.ingested_at > cutoff:
            raise ValueError("snapshot contains an event ingested after its cutoff")
    if any(label.reported_at > cutoff for label in labels):
        raise ValueError("snapshot contains a label reported after its cutoff")

    subjects: dict[str, str | None] = {}
    for session_id in sessions:
        values = {event.subject_id for event in lifecycle
                  if event.session_id == session_id and event.subject_id is not None}
        if len(values) > 1:
            raise ValueError("session lifecycle contains inconsistent subjects")
        subjects[session_id] = next(iter(values), None)

    windows: dict[UUID, dict[str, Any]] = {}
    for item in snapshot.get("windows", []):
        window_id = UUID(str(item["window_id"]))
        if window_id in windows:
            raise ValueError("duplicate completed window")
        if item["session_id"] not in sessions:
            raise ValueError("window references an unavailable session")
        start, end = datetime.fromisoformat(item["window_start"]), datetime.fromisoformat(item["window_end"])
        if _utc(end) - _utc(start) != timedelta(minutes=5) or _utc(end) > cutoff:
            raise ValueError("snapshot contains an incomplete or future window")
        windows[window_id] = item

    activity_by_window = _unique_by_window(activity, "behavioral")
    cv_by_window = _unique_by_window(cv_events, "CV")
    labels_by_session: dict[str, list[EffortLabelEvent]] = defaultdict(list)
    for label in labels:
        labels_by_session[label.session_id].append(label)
    latest_labels: dict[UUID, EffortLabelEvent] = {}
    for history in labels_by_session.values():
        validate_label_history(history)
        for label in sorted(history, key=lambda item: (item.reported_at, str(item.label_id))):
            latest_labels[label.window_id] = label

    rows: list[MultimodalDatasetRow] = []
    source_events: list[dict[str, str]] = []
    for window_id, window in sorted(windows.items(), key=lambda item: (item[1]["window_start"], str(item[0]))):
        behavior = activity_by_window.get(window_id)
        target_label = latest_labels.get(window_id)
        if behavior is None or target_label is None:
            continue
        expected = (
            window["session_id"], _utc(datetime.fromisoformat(window["window_start"])),
            _utc(datetime.fromisoformat(window["window_end"])),
        )
        for event in (behavior, target_label):
            if (event.session_id, event.window_start, event.window_end) != expected:
                raise ValueError("event boundaries do not match the completed window")
        cv = cv_by_window.get(window_id)
        if cv is not None and (cv.session_id, cv.window_start, cv.window_end) != expected:
            raise ValueError("CV boundaries do not match the completed window")
        cv_available: Literal[0, 1] = 1 if cv is not None and cv.camera_available else 0
        frame_drop_ratio = (
            cv.frames_dropped / cv.frames_sampled if cv_available and cv and cv.frames_sampled else None
        )
        session_id = window["session_id"]
        subject = subjects[session_id]
        row = MultimodalDatasetRow(
            session_key=_pseudonym("session", session_id),
            subject_key=_pseudonym("subject", subject) if subject is not None else None,
            session_kind=sessions[session_id]["session_kind"],
            window_id=window_id,
            window_start=expected[1], window_end=expected[2], feature_cutoff=expected[2],
            dataset_snapshot_cutoff=cutoff,
            behavioral_event_id=behavior.event_id,
            cv_event_id=cv.event_id if cv is not None else None,
            label_event_id=target_label.event_id,
            active_seconds=behavior.active_seconds, idle_seconds=behavior.idle_seconds,
            keyboard_event_count=behavior.keyboard_event_count,
            pointer_event_count=behavior.pointer_event_count,
            application_switch_count=behavior.application_switch_count,
            build_count=behavior.build_count, test_count=behavior.test_count,
            face_presence_ratio=cv.face_presence_ratio if cv_available and cv else None,
            gaze_away_ratio=cv.gaze_away_ratio if cv_available and cv else None,
            blink_rate_per_minute=cv.blink_rate_per_minute if cv_available and cv else None,
            head_pose_variance=cv.head_pose_variance if cv_available and cv else None,
            frame_drop_ratio=frame_drop_ratio,
            cv_available=cv_available,
            self_reported_effort=target_label.effort_rating,
        )
        rows.append(row)
        for source_event in (behavior, cv, target_label):
            if source_event is not None:
                payload = source_event.model_dump(mode="json")
                source_events.append({"event_id": str(source_event.event_id), "sha256": sha256_bytes(_canonical(payload))})

    if len({row.window_id for row in rows}) != len(rows):
        raise ValueError("dataset contains duplicate windows")
    lineage = {
        "source": snapshot.get("source", "sqlite://focus-session-store"),
        "source_snapshot_sha256": _snapshot_digest(snapshot),
        "source_events": sorted(source_events, key=lambda item: item["event_id"]),
        "excluded_windows": len(windows) - len(rows),
    }
    return rows, lineage


def _jsonl(rows: list[MultimodalDatasetRow]) -> bytes:
    return b"".join(_canonical(row.model_dump(mode="json")) + b"\n" for row in rows)


def build_split_manifest(
    rows: list[MultimodalDatasetRow], dataset_sha256: str, *, random_seed: int
) -> dict[str, Any]:
    """Freeze chronological whole-group splits or explain why no valid split exists."""

    base: dict[str, Any] = {
        "contract_version": "1.0",
        "dataset_sha256": dataset_sha256,
        "random_seed": random_seed,
        "policy": "chronological 60/20/20 whole groups; subjects when >=3, else sessions",
        "status": "INSUFFICIENT_DATA",
        "reasons": [],
        "splits": {"train": [], "validation": [], "test": []},
    }
    if len(rows) < MINIMUM_ROWS:
        base["reasons"].append(f"requires at least {MINIMUM_ROWS} labeled windows")
        return base

    subjects = {row.subject_key for row in rows if row.subject_key is not None}
    if len(subjects) == 2:
        base["reasons"].append("two subjects cannot form three subject-disjoint splits")
        return base
    group_field = "subject_key" if len(subjects) >= 3 else "session_key"
    population_scope = "multi_subject" if group_field == "subject_key" else (
        "within_subject" if len(subjects) == 1 else "subject_unknown"
    )
    grouped: dict[str, list[MultimodalDatasetRow]] = defaultdict(list)
    for row in rows:
        key = getattr(row, group_field)
        if key is None:
            base["reasons"].append("subject grouping requires a subject on every row")
            return base
        grouped[key].append(row)
    groups = sorted(
        grouped,
        key=lambda key: (min(row.window_start for row in grouped[key]), key),
    )
    if len(groups) < 3:
        base["reasons"].append("requires at least three indivisible split groups")
        return base
    train_end = max(1, int(len(groups) * 0.6))
    validation_end = max(train_end + 1, int(len(groups) * 0.8))
    validation_end = min(validation_end, len(groups) - 1)
    group_splits = {
        "train": groups[:train_end],
        "validation": groups[train_end:validation_end],
        "test": groups[validation_end:],
    }
    if any(not values for values in group_splits.values()):
        base["reasons"].append("group allocation produced an empty split")
        return base
    split_rows = {
        name: sorted(
            (row for key in keys for row in grouped[key]),
            key=lambda row: (row.window_start, str(row.window_id)),
        )
        for name, keys in group_splits.items()
    }
    if not (
        max(row.window_end for row in split_rows["train"])
        <= min(row.window_start for row in split_rows["validation"])
        and max(row.window_end for row in split_rows["validation"])
        <= min(row.window_start for row in split_rows["test"])
    ):
        base["reasons"].append("group chronology overlaps across splits")
        return base
    for name in ("train", "validation"):
        bands = {effort_band(row.self_reported_effort).value for row in split_rows[name]}
        if bands != set(BANDS):
            base["reasons"].append(f"{name} lacks all compatibility bands")
    test_support = Counter(effort_band(row.self_reported_effort).value for row in split_rows["test"])
    if any(test_support[band] < 5 for band in BANDS):
        base["reasons"].append("test requires at least five rows per compatibility band")
    train_cv = {row.cv_available for row in split_rows["train"]}
    if train_cv != {0, 1}:
        base["reasons"].append("multimodal training requires both present and missing CV")
    if base["reasons"]:
        return base
    base.update(
        {
            "status": "PASS",
            "group_field": group_field,
            "population_scope": population_scope,
            "groups": group_splits,
            "splits": {
                name: [str(row.window_id) for row in values] for name, values in split_rows.items()
            },
            "counts": {name: len(values) for name, values in split_rows.items()},
            "test_band_support": dict(sorted(test_support.items())),
        }
    )
    return base


def write_dataset_bundle(
    snapshot: dict[str, Any], dataset_path: Path, manifest_path: Path, split_path: Path,
    *, git_revision: str, random_seed: int, data_provenance: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows, lineage = build_dataset_rows(snapshot)
    payload = _jsonl(rows)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_bytes(payload)
    dataset_sha256 = sha256_bytes(payload)
    split_manifest = build_split_manifest(rows, dataset_sha256, random_seed=random_seed)
    split_payload = _canonical(split_manifest) + b"\n"
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_bytes(split_payload)
    distribution = Counter(str(row.self_reported_effort) for row in rows)
    band_distribution = Counter(effort_band(row.self_reported_effort).value for row in rows)
    subjects = {row.subject_key for row in rows if row.subject_key is not None}
    manifest = {
        "contract_version": "1.0",
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "behavioral_feature_schema_version": "1.0",
        "cv_feature_schema_version": "1.0",
        "target_definition_version": TARGET_VERSION,
        "target": "self_reported_effort",
        "target_range": [1, 7],
        "data_provenance": data_provenance,
        "dataset_snapshot_cutoff": snapshot["snapshot_cutoff"],
        "row_count": len(rows),
        "valid_label_count": len(rows),
        "paired_cv_count": sum(row.cv_available for row in rows),
        "missing_cv_count": sum(not row.cv_available for row in rows),
        "cv_coverage": sum(row.cv_available for row in rows) / len(rows) if rows else 0.0,
        "target_distribution": dict(sorted(distribution.items())),
        "band_distribution": dict(sorted(band_distribution.items())),
        "session_count": len({row.session_key for row in rows}),
        "subject_count": len(subjects),
        "subject_grouping": "available" if subjects else "unavailable",
        "behavioral_feature_names": list(BEHAVIORAL_FEATURES),
        "cv_feature_names": list(CV_FEATURES),
        "multimodal_feature_names": list(MULTIMODAL_FEATURES),
        "missingness": "CV numeric values are null and cv_available=0 when unobserved",
        "split_policy": split_manifest["policy"],
        "random_seed": random_seed,
        "dataset_sha256": dataset_sha256,
        "split_manifest_sha256": sha256_bytes(split_payload),
        "git_revision": git_revision,
        **lineage,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(_canonical(manifest) + b"\n")
    return manifest, split_manifest


def load_dataset(dataset_path: Path) -> list[MultimodalDatasetRow]:
    rows = [MultimodalDatasetRow.model_validate_json(line)
            for line in dataset_path.read_text().splitlines() if line]
    if len({row.window_id for row in rows}) != len(rows):
        raise ValueError("dataset contains duplicate windows")
    return rows


def synthetic_snapshot(*, samples: int = 90, seed: int = 42) -> dict[str, Any]:
    """Build a contract-valid fixture; its labels are synthetic engineering data."""

    if samples < 90 or samples % 9:
        raise ValueError("synthetic fixture samples must be at least 90 and divisible by 9")
    base = datetime(2026, 1, 1, 8, 0, 0, 123456, tzinfo=UTC)
    per_session = samples // 9
    snapshot: dict[str, Any] = {
        "source": "synthetic://cogniflow/multimodal-pipeline-fixture-v1",
        "data_provenance": "synthetic_pipeline_fixture",
        "sessions": [], "windows": [], "lifecycle": [], "activity": [], "cv": [], "labels": [],
    }
    for session_index in range(9):
        session_id = f"fixture-session-{session_index:02d}"
        session_start = base + timedelta(days=session_index)
        snapshot["sessions"].append(
            {
                "session_id": session_id, "session_kind": "programming",
                "privacy_mode": "behavioral_cv", "state": "session.completed",
                "created_at": session_start.isoformat(),
            }
        )
        lifecycle = SessionLifecycleEvent(
            event_id=uuid5(NAMESPACE_URL, f"fixture:lifecycle:{session_id}"),
            session_id=session_id, subject_id="fixture_subject_01", event_time=session_start,
            ingested_at=session_start, source="synthetic_fixture", producer_version="1.0.0",
            idempotency_key=f"{session_id}:started", event_type="session.started", sequence=1,
            session_kind="programming", privacy_mode="behavioral_cv",
        )
        snapshot["lifecycle"].append(lifecycle.model_dump(mode="json"))
        for offset in range(per_session):
            index = session_index * per_session + offset
            start = session_start + timedelta(minutes=5 * offset)
            end = start + timedelta(minutes=5)
            window_id = uuid5(NAMESPACE_URL, f"cogniflow:{session_id}:{start.isoformat()}:{end.isoformat()}")
            snapshot["windows"].append(
                {"window_id": str(window_id), "session_id": session_id,
                 "window_start": start.isoformat(), "window_end": end.isoformat()}
            )
            active = float(120 + (index * 17 + seed) % 181)
            behavior = BehavioralActivityEvent(
                event_id=uuid5(NAMESPACE_URL, f"fixture:behavior:{window_id}"),
                session_id=session_id, subject_id="fixture_subject_01", event_time=end,
                ingested_at=end + timedelta(microseconds=1), source="synthetic_fixture",
                producer_version="1.0.0", idempotency_key=f"{session_id}:behavior:{offset}",
                window_id=window_id, window_start=start, window_end=end, feature_cutoff=end,
                active_seconds=active, idle_seconds=300 - active,
                keyboard_event_count=20 + index % 80, pointer_event_count=10 + index % 40,
                application_switch_count=index % 8,
                build_count=None if index % 4 == 0 else index % 5,
                test_count=None if index % 5 == 0 else index % 7,
            )
            snapshot["activity"].append(behavior.model_dump(mode="json"))
            if index % 5:
                sampled = 3000
                dropped = index % 11
                cv = CvFeatureWindowEvent(
                    event_id=uuid5(NAMESPACE_URL, f"fixture:cv:{window_id}"),
                    session_id=session_id, subject_id="fixture_subject_01", event_time=end,
                    ingested_at=end + timedelta(microseconds=2), source="synthetic_fixture",
                    producer_version="1.0.0", idempotency_key=f"{session_id}:cv:{offset}",
                    window_id=window_id, window_start=start, window_end=end, feature_cutoff=end,
                    camera_available=True, face_presence_ratio=0.85 + (index % 10) / 100,
                    gaze_away_ratio=(index % 6) / 10, blink_rate_per_minute=8 + index % 12,
                    head_pose_variance=0.1 + (index % 9) / 10,
                    frames_sampled=sampled, frames_processed=sampled - dropped,
                    frames_dropped=dropped, agent_version="1.0.0",
                    asset_name="fixture_asset", asset_sha256="a" * 64,
                    cpu_seconds=3.0, latency_p50_ms=5.0, latency_p95_ms=8.0,
                )
                snapshot["cv"].append(cv.model_dump(mode="json"))
            rating = (1, 3, 6)[index % 3]
            label = EffortLabelEvent(
                event_id=uuid5(NAMESPACE_URL, f"fixture:label:{window_id}:1"),
                label_id=uuid5(NAMESPACE_URL, f"fixture:label-id:{window_id}:1"),
                session_id=session_id, subject_id="fixture_subject_01",
                event_time=end + timedelta(seconds=30), ingested_at=end + timedelta(seconds=30),
                source="synthetic_fixture", producer_version="1.0.0",
                idempotency_key=f"{session_id}:label:{offset}:1", window_id=window_id,
                window_start=start, window_end=end, feature_cutoff=end,
                effort_rating=rating, reported_at=end + timedelta(seconds=30),
            )
            snapshot["labels"].append(label.model_dump(mode="json"))
            if index == 0:
                correction = label.model_copy(
                    update={
                        "event_id": uuid5(NAMESPACE_URL, f"fixture:label:{window_id}:2"),
                        "label_id": uuid5(NAMESPACE_URL, f"fixture:label-id:{window_id}:2"),
                        "event_time": end + timedelta(seconds=40),
                        "ingested_at": end + timedelta(seconds=40),
                        "idempotency_key": f"{session_id}:label:{offset}:2",
                        "reported_at": end + timedelta(seconds=40),
                        "effort_rating": 2,
                        "supersedes_label_id": label.label_id,
                    }
                )
                snapshot["labels"].append(correction.model_dump(mode="json"))
    cutoff = max(datetime.fromisoformat(item["event_time"]) for item in snapshot["labels"])
    snapshot["snapshot_cutoff"] = (cutoff + timedelta(seconds=1)).isoformat()
    return snapshot


def _candidate_models(random_seed: int) -> dict[str, Any]:
    return {
        "dummy_median": Pipeline(
            [("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
             ("regressor", DummyRegressor(strategy="median"))]
        ),
        "ridge": Pipeline(
            [("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
             ("scaler", StandardScaler()), ("regressor", Ridge(alpha=1.0))]
        ),
        "random_forest": Pipeline(
            [("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
             ("regressor", RandomForestRegressor(
                 n_estimators=100, max_depth=8, random_state=random_seed, n_jobs=1
             ))]
        ),
    }


def _model_config(name: str, random_seed: int) -> dict[str, Any]:
    configs: dict[str, dict[str, Any]] = {
        "dummy_median": {"strategy": "median"},
        "ridge": {"alpha": 1.0},
        "random_forest": {
            "n_estimators": 100, "max_depth": 8,
            "random_state": random_seed, "n_jobs": 1,
        },
    }
    return configs[name]


def _band(value: float) -> str:
    return effort_band(min(7.0, max(1.0, float(value)))).value


def _metrics(expected: Any, predicted: Any, latencies_ms: list[float]) -> dict[str, Any]:
    bounded = [min(7.0, max(1.0, float(value))) for value in predicted]
    expected_bands = [_band(value) for value in expected]
    predicted_bands = [_band(value) for value in bounded]
    precision, recall, _, support = precision_recall_fscore_support(
        expected_bands, predicted_bands, labels=BANDS, zero_division=0
    )
    ordered_latency = sorted(latencies_ms)
    p95_index = min(len(ordered_latency) - 1, int(len(ordered_latency) * 0.95))
    return {
        "sample_count": len(bounded),
        "mae": mean_absolute_error(expected, bounded),
        "macro_f1": f1_score(expected_bands, predicted_bands, labels=BANDS,
                             average="macro", zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(expected_bands, predicted_bands),
        "per_class_precision": dict(zip(BANDS, precision.tolist())),
        "per_class_recall": dict(zip(BANDS, recall.tolist())),
        "per_class_support": dict(zip(BANDS, support.tolist())),
        "confusion_matrix": confusion_matrix(expected_bands, predicted_bands, labels=BANDS).tolist(),
        "prediction_distribution": dict(sorted(Counter(predicted_bands).items())),
        "prediction_min": min(bounded),
        "prediction_max": max(bounded),
        "latency_p50_ms": statistics.median(ordered_latency),
        "latency_p95_ms": ordered_latency[p95_index],
    }


def _predict_with_latency(model: Any, frame: pd.DataFrame, features: tuple[str, ...]) -> tuple[list[float], list[float]]:
    predictions, latencies = [], []
    for index in range(len(frame)):
        started = time.perf_counter()
        value = float(model.predict(frame.iloc[[index]][list(features)])[0])
        latencies.append((time.perf_counter() - started) * 1000)
        predictions.append(value)
    return predictions, latencies


def _split_frames(
    rows: list[MultimodalDatasetRow], split_manifest: dict[str, Any]
) -> dict[str, pd.DataFrame]:
    by_id = {str(row.window_id): row.model_dump(mode="json") for row in rows}
    expected_ids = {item for values in split_manifest["splits"].values() for item in values}
    if expected_ids != set(by_id) or sum(map(len, split_manifest["splits"].values())) != len(rows):
        raise ValueError("split manifest does not partition the dataset exactly once")
    result = {
        name: pd.DataFrame([by_id[window_id] for window_id in split_manifest["splits"][name]])
        for name in ("train", "validation", "test")
    }
    sets = [set(frame["window_id"]) for frame in result.values()]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
        raise ValueError("split windows overlap")
    return result


def _cohort_ready(frames: dict[str, pd.DataFrame], *, cv_only: bool = False) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    selected = {
        name: frame[frame["cv_available"] == 1].copy() if cv_only else frame
        for name, frame in frames.items()
    }
    if any(len(frame) < 15 for frame in selected.values()):
        reasons.append("each split requires at least 15 eligible rows")
    for name in ("train", "validation"):
        if set(selected[name].get("self_reported_effort", pd.Series(dtype=int)).map(_band)) != set(BANDS):
            reasons.append(f"{name} lacks all compatibility bands")
    if cv_only:
        support = Counter(selected["test"].get("self_reported_effort", pd.Series(dtype=int)).map(_band))
        if any(support[band] < 5 for band in BANDS):
            reasons.append("paired test requires at least five rows per compatibility band")
    return not reasons, reasons


def _log_mlflow_candidate(
    model: Any, model_path: Path, experiment_name: str, modality: str,
    manifest: dict[str, Any], split_manifest: dict[str, Any], result: dict[str, Any],
    *, tracking_uri: str, register_candidates: bool,
) -> dict[str, str]:
    import mlflow
    import mlflow.sklearn

    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient()
    if client.get_experiment_by_name(experiment_name) is None:
        artifact_location = None
        if tracking_uri.startswith("sqlite:///"):
            database = Path(tracking_uri.removeprefix("sqlite:///")).resolve()
            artifact_location = (database.parent / "mlartifacts" / experiment_name).as_uri()
        mlflow.create_experiment(experiment_name, artifact_location=artifact_location)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=f"experiment-{modality}") as run:
        mlflow.set_tags(
            {
                "approval_status": "candidate",
                "validation_scope": result["validation_scope"],
                "target_version": TARGET_VERSION,
                "git_revision": manifest["git_revision"],
            }
        )
        mlflow.log_params(
            {
                "modality": modality,
                "model_type": result["selected_model"],
                "dataset_sha256": manifest["dataset_sha256"],
                "split_manifest_sha256": manifest["split_manifest_sha256"],
                "random_seed": split_manifest["random_seed"],
                "feature_names": json.dumps(result["feature_names"]),
            }
        )
        mlflow.log_metrics(
            {
                "validation_mae": result["validation"]["mae"],
                "validation_macro_f1": result["validation"]["macro_f1"],
                "test_mae": result["test"]["mae"],
                "test_macro_f1": result["test"]["macro_f1"],
            }
        )
        mlflow.log_artifact(str(model_path), artifact_path="candidate")
        registration: dict[str, str] = {
            "mlflow_run_id": run.info.run_id,
            "approval_status": "candidate",
        }
        if register_candidates:
            if result["validation_scope"] != "empirical_evaluation":
                raise ValueError("synthetic engineering candidates cannot be registered")
            info = mlflow.sklearn.log_model(model, artifact_path="model")
            version = mlflow.register_model(info.model_uri, f"cogniflow-effort-{modality}-experimental")
            client.set_model_version_tag(version.name, version.version, "approval_status", "candidate")
            registration.update({"model_name": version.name, "model_version": str(version.version)})
        return registration


def run_experiments(
    dataset_path: Path, manifest_path: Path, split_path: Path, output_dir: Path,
    report_path: Path, *, tracking_uri: str, experiment_name: str,
    validation_scope: Literal["engineering_validation", "empirical_evaluation"],
    register_candidates: bool = False,
) -> dict[str, Any]:
    """Run deterministic CPU-only A/B/C regression without changing serving state."""

    manifest = json.loads(manifest_path.read_text())
    split_manifest = json.loads(split_path.read_text())
    if manifest.get("dataset_sha256") != sha256_file(dataset_path):
        raise ValueError("dataset manifest checksum mismatch")
    if manifest.get("split_manifest_sha256") != sha256_file(split_path):
        raise ValueError("split manifest checksum mismatch")
    if split_manifest.get("dataset_sha256") != manifest["dataset_sha256"]:
        raise ValueError("dataset and split lineage disagree")
    if split_manifest.get("status") != "PASS":
        result = {
            "status": "INSUFFICIENT_DATA", "reasons": split_manifest.get("reasons", []),
            "validation_scope": validation_scope, "models_registered": 0,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(_canonical(result) + b"\n")
        return result
    rows = load_dataset(dataset_path)
    frames = _split_frames(rows, split_manifest)
    ready, reasons = _cohort_ready(frames)
    if not ready:
        result = {"status": "INSUFFICIENT_DATA", "reasons": reasons,
                  "validation_scope": validation_scope, "models_registered": 0}
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(_canonical(result) + b"\n")
        return result

    output_dir.mkdir(parents=True, exist_ok=True)
    specifications = {
        "A": (BEHAVIORAL_FEATURES, False),
        "B": (CV_FEATURES, True),
        "C": (MULTIMODAL_FEATURES, False),
    }
    experiments: dict[str, Any] = {}
    models: dict[str, Any] = {}
    cv_ready, cv_reasons = _cohort_ready(frames, cv_only=True)
    for modality, (features, cv_only) in specifications.items():
        if cv_only and not cv_ready:
            experiments[modality] = {
                "status": "INSUFFICIENT_DATA", "reasons": cv_reasons,
                "feature_names": list(features),
            }
            continue
        cohort = {
            name: frame[frame["cv_available"] == 1].copy() if cv_only else frame.copy()
            for name, frame in frames.items()
        }
        validation_candidates: dict[str, Any] = {}
        candidates = _candidate_models(int(split_manifest["random_seed"]))
        for name, model in candidates.items():
            cpu_start, wall_start = time.process_time(), time.perf_counter()
            model.fit(cohort["train"][list(features)], cohort["train"]["self_reported_effort"])
            predicted, latency = _predict_with_latency(model, cohort["validation"], features)
            validation_candidates[name] = {
                "metrics": _metrics(cohort["validation"]["self_reported_effort"], predicted, latency),
                "training_cpu_seconds": time.process_time() - cpu_start,
                "training_wall_seconds": time.perf_counter() - wall_start,
            }
        selected_name = min(
            validation_candidates,
            key=lambda name: (validation_candidates[name]["metrics"]["mae"], name),
        )
        selected = candidates[selected_name]
        test_predictions, test_latency = _predict_with_latency(selected, cohort["test"], features)
        model_path = output_dir / f"experiment-{modality}.joblib"
        joblib.dump(selected, model_path)
        skops_path = output_dir / f"experiment-{modality}.skops"
        skops.io.dump(selected, skops_path)
        experiments[modality] = {
            "status": "PASS", "feature_names": list(features), "selected_model": selected_name,
            "validation_candidates": validation_candidates,
            "validation": validation_candidates[selected_name]["metrics"],
            "test": _metrics(cohort["test"]["self_reported_effort"], test_predictions, test_latency),
            "counts": {name: len(frame) for name, frame in cohort.items()},
            "excluded_missing_cv": {
                name: len(frames[name]) - len(cohort[name]) for name in cohort
            },
            "model_sha256": sha256_file(model_path),
            "model_skops_sha256": sha256_file(skops_path),
            "model_config": _model_config(selected_name, int(split_manifest["random_seed"])),
            "skops_untrusted_types": sorted(skops.io.get_untrusted_types(file=skops_path)),
            "validation_scope": validation_scope,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        }
        models[modality] = selected

    if experiments.get("A", {}).get("status") == "PASS" and experiments.get("C", {}).get("status") == "PASS":
        a, c = experiments["A"]["validation"], experiments["C"]["validation"]
        prefer_c = (
            a["mae"] - c["mae"] >= SELECTION_MAE_MARGIN
            and c["macro_f1"] >= a["macro_f1"] - SELECTION_F1_TOLERANCE
        )
        preferred = "C" if prefer_c else "A"
    else:
        preferred = "A"

    paired: dict[str, Any] = {"status": "INSUFFICIENT_DATA", "reasons": cv_reasons}
    if cv_ready and all(experiments.get(name, {}).get("status") == "PASS" for name in ("A", "B", "C")):
        paired_test = frames["test"][frames["test"]["cv_available"] == 1].copy()
        paired = {"status": "PASS", "window_ids": list(paired_test["window_id"]), "metrics": {}}
        for modality, (features, _) in specifications.items():
            predicted, latency = _predict_with_latency(models[modality], paired_test, features)
            paired["metrics"][modality] = _metrics(
                paired_test["self_reported_effort"], predicted, latency
            )

    result = {
        "status": "PASS",
        "warning": (
            "Synthetic fixture metrics validate engineering only, not predictive accuracy."
            if validation_scope == "engineering_validation"
            else "Local user-label evaluation is within the recorded population scope only."
        ),
        "validation_scope": validation_scope,
        "target": "self_reported_effort",
        "dataset_sha256": manifest["dataset_sha256"],
        "split_manifest_sha256": manifest["split_manifest_sha256"],
        "population_scope": split_manifest["population_scope"],
        "cv_coverage": manifest["cv_coverage"],
        "experiments": experiments,
        "paired_cv_present_evaluation": paired,
        "full_cohort_comparison": {name: experiments[name]["test"] for name in ("A", "C")},
        "selection_rule": {
            "preferred_default": "A",
            "c_mae_improvement_required": SELECTION_MAE_MARGIN,
            "c_macro_f1_tolerance": SELECTION_F1_TOLERANCE,
            "uses": "validation_only",
        },
        "runtime_versions": {
            name: importlib.metadata.version(name)
            for name in ("python", "numpy", "pandas", "scikit-learn", "skops")
            if name != "python"
        } | {"python": ".".join(map(str, __import__("sys").version_info[:3]))},
        "preferred_candidate": preferred,
        "models_registered": 0,
        "mlflow": {},
    }
    for modality, model in models.items():
        registration = _log_mlflow_candidate(
            model, output_dir / f"experiment-{modality}.joblib", experiment_name, modality,
            manifest, split_manifest, experiments[modality], tracking_uri=tracking_uri,
            register_candidates=register_candidates,
        )
        result["mlflow"][modality] = registration
        result["models_registered"] += int("model_version" in registration)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(_canonical(result) + b"\n")
    return result
