"""Transform validated Bronze events into an idempotent Delta Silver table."""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from delta.tables import DeltaTable
from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession, functions as F, types as T

from cogniflow_data.storage_accounting import list_objects, prefix_evidence

LAKEHOUSE_BUCKET = os.getenv("MINIO_LAKEHOUSE_BUCKET", "cogniflow-lakehouse")
SILVER_URI = f"s3a://{LAKEHOUSE_BUCKET}/silver/session_features"
BEHAVIORAL_SILVER_URI = f"s3a://{LAKEHOUSE_BUCKET}/silver/behavioral_features"
SILVER_SCHEMA = T.StructType(
    [
        T.StructField("event_id", T.StringType(), False),
        T.StructField("session_id", T.StringType(), False),
        T.StructField("user_id", T.StringType(), True),
        T.StructField("event_time", T.TimestampType(), False),
        T.StructField("ingested_at", T.TimestampType(), False),
        T.StructField("schema_version", T.StringType(), False),
        T.StructField("source", T.StringType(), False),
        T.StructField("focus_minutes", T.LongType(), False),
        T.StructField("distraction_minutes", T.LongType(), False),
        T.StructField("tasks_due", T.LongType(), False),
        T.StructField("hours_to_deadline", T.DoubleType(), False),
        T.StructField("kafka_topic", T.StringType(), False),
        T.StructField("kafka_partition", T.LongType(), False),
        T.StructField("kafka_offset", T.LongType(), False),
    ]
)
BEHAVIORAL_SCHEMA = T.StructType(
    [
        T.StructField("event_id", T.StringType(), False),
        T.StructField("session_id", T.StringType(), False),
        T.StructField("window_id", T.StringType(), False),
        T.StructField("window_start", T.TimestampType(), False),
        T.StructField("window_end", T.TimestampType(), False),
        T.StructField("feature_cutoff", T.TimestampType(), False),
        T.StructField("schema_version", T.StringType(), False),
        T.StructField("source", T.StringType(), False),
        T.StructField("active_seconds", T.DoubleType(), False),
        T.StructField("idle_seconds", T.DoubleType(), False),
        T.StructField("keyboard_event_count", T.LongType(), False),
        T.StructField("pointer_event_count", T.LongType(), False),
        T.StructField("application_switch_count", T.LongType(), False),
        T.StructField("build_count", T.LongType(), True),
        T.StructField("test_count", T.LongType(), True),
        T.StructField("kafka_topic", T.StringType(), False),
        T.StructField("kafka_partition", T.LongType(), False),
        T.StructField("kafka_offset", T.LongType(), False),
    ]
)
BRONZE_SESSION_SCHEMA = T.StructType(
    [
        T.StructField(
            "event",
            T.StructType(
                [
                    T.StructField("event_id", T.StringType(), True),
                    T.StructField("session_id", T.StringType(), True),
                    T.StructField("user_id", T.StringType(), True),
                    T.StructField("event_time", T.StringType(), True),
                    T.StructField("ingested_at", T.StringType(), True),
                    T.StructField("schema_version", T.StringType(), True),
                    T.StructField("event_type", T.StringType(), True),
                    T.StructField("source", T.StringType(), True),
                    T.StructField(
                        "payload",
                        T.StructType(
                            [
                                T.StructField("focus_minutes", T.LongType(), True),
                                T.StructField("distraction_minutes", T.LongType(), True),
                                T.StructField("tasks_due", T.LongType(), True),
                                T.StructField("hours_to_deadline", T.DoubleType(), True),
                            ]
                        ),
                        True,
                    ),
                ]
            ),
            True,
        ),
        T.StructField(
            "kafka",
            T.StructType(
                [
                    T.StructField("topic", T.StringType(), True),
                    T.StructField("partition", T.LongType(), True),
                    T.StructField("offset", T.LongType(), True),
                ]
            ),
            True,
        ),
        T.StructField("_corrupt_record", T.StringType(), True),
    ]
)


def validate_event(value: dict) -> dict:
    """Validate the v1 wire contract inside Spark's Python 3.8 runtime."""

    if value.get("schema_version") != "1.0" or value.get("event_type") != "session.snapshot":
        raise ValueError("unsupported event schema")
    payload = value["payload"]
    limits = {
        "focus_minutes": (0, 1440),
        "distraction_minutes": (0, 1440),
        "tasks_due": (0, 1000),
        "hours_to_deadline": (0, 87600),
    }
    for field, (minimum, maximum) in limits.items():
        if field not in payload or not minimum <= float(payload[field]) <= maximum:
            raise ValueError(f"invalid {field}")
    for field in ("event_time", "ingested_at"):
        parsed = datetime.fromisoformat(value[field].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError(f"naive {field}")
    return value


def validate_behavioral_event(value: dict) -> dict:
    """Validate the privacy-minimal completed behavioral window contract."""

    if value.get("schema_version") != "1.0" or value.get("event_type") != "behavioral.window":
        raise ValueError("unsupported behavioral schema")
    allowed = {
        "schema_version", "event_id", "session_id", "subject_id", "event_time", "ingested_at",
        "source", "producer_version", "idempotency_key", "event_type", "window_id",
        "window_start", "window_end", "feature_cutoff", "active_seconds", "idle_seconds",
        "keyboard_event_count", "pointer_event_count", "application_switch_count", "build_count",
        "test_count",
    }
    if set(value) - allowed:
        raise ValueError("unknown behavioral field")
    timestamps = {
        field: datetime.fromisoformat(value[field].replace("Z", "+00:00"))
        for field in ("event_time", "ingested_at", "window_start", "window_end", "feature_cutoff")
    }
    if any(timestamp.tzinfo is None for timestamp in timestamps.values()):
        raise ValueError("naive behavioral timestamp")
    if not (
        (timestamps["window_end"] - timestamps["window_start"]).total_seconds() == 300
        and timestamps["event_time"] == timestamps["feature_cutoff"] == timestamps["window_end"]
        and timestamps["ingested_at"] >= timestamps["event_time"]
    ):
        raise ValueError("invalid behavioral chronology")
    limits = {
        "active_seconds": (0, 300), "idle_seconds": (0, 300),
        "keyboard_event_count": (0, 1_000_000), "pointer_event_count": (0, 1_000_000),
        "application_switch_count": (0, 100_000),
    }
    for field, (minimum, maximum) in limits.items():
        if field not in value or not minimum <= float(value[field]) <= maximum:
            raise ValueError(f"invalid {field}")
    if float(value["active_seconds"]) + float(value["idle_seconds"]) > 300:
        raise ValueError("invalid activity duration")
    return value


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=30,
            retries={"max_attempts": 2},
        ),
    )


def _listed_objects(client, bucket: str, prefix: str) -> list[dict]:
    return list_objects(client, bucket, prefix)


def load_bronze_accounted(client=None) -> tuple[list[dict], list[dict], dict[str, int]]:
    client = client or s3_client()
    bucket = os.getenv("MINIO_BRONZE_BUCKET", "cogniflow-bronze")
    valid, rejected = [], []
    input_bytes = 0
    input_rows = 0
    objects = _listed_objects(client, bucket, "session_events/")
    for item in objects:
        body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"].read()
        input_bytes += len(body)
        for line in body.splitlines():
            if not line:
                continue
            input_rows += 1
            try:
                row = json.loads(line)
                event = validate_event(row["event"])
                payload = event["payload"]
                valid.append(
                    {
                        "event_id": event["event_id"],
                        "session_id": event["session_id"],
                        "user_id": event.get("user_id"),
                        "event_time": datetime.fromisoformat(event["event_time"].replace("Z", "+00:00")).astimezone(timezone.utc),
                        "ingested_at": datetime.fromisoformat(event["ingested_at"].replace("Z", "+00:00")).astimezone(timezone.utc),
                        "schema_version": event["schema_version"],
                        "source": event["source"],
                        "focus_minutes": payload["focus_minutes"],
                        "distraction_minutes": payload["distraction_minutes"],
                        "tasks_due": payload["tasks_due"],
                        "hours_to_deadline": float(payload["hours_to_deadline"]),
                        "kafka_topic": row["kafka"]["topic"],
                        "kafka_partition": row["kafka"]["partition"],
                        "kafka_offset": row["kafka"]["offset"],
                    }
                )
            except Exception as exc:
                rejected.append({"object_key": item["Key"], "error": type(exc).__name__})
    return valid, rejected, {
        "spark_input_bytes": input_bytes,
        "bronze_rows_read": input_rows,
        "bronze_objects_read": len(objects),
    }


def load_bronze() -> tuple[list[dict], list[dict]]:
    valid, rejected, _accounting = load_bronze_accounted()
    return valid, rejected


def load_behavioral_bronze() -> tuple[list[dict], list[dict]]:
    client = s3_client()
    bucket = os.getenv("MINIO_BRONZE_BUCKET", "cogniflow-bronze")
    valid, rejected = [], []
    for item in _listed_objects(client, bucket, "behavioral_activity/"):
        body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"]
        for line in body.iter_lines():
            try:
                row = json.loads(line)
                event = validate_behavioral_event(row["event"])
                valid.append({
                    **{field: event.get(field) for field in (
                        "event_id", "session_id", "window_id", "schema_version",
                        "active_seconds", "idle_seconds", "keyboard_event_count",
                        "pointer_event_count", "application_switch_count", "build_count", "test_count",
                    )},
                    **{field: datetime.fromisoformat(event[field].replace("Z", "+00:00")).astimezone(timezone.utc)
                       for field in ("window_start", "window_end", "feature_cutoff")},
                    "source": f"{event['source']}:cogniflow.behavioral-activity.v1",
                    "kafka_topic": row["kafka"]["topic"],
                    "kafka_partition": row["kafka"]["partition"],
                    "kafka_offset": row["kafka"]["offset"],
                })
            except Exception as exc:
                rejected.append({"object_key": item["Key"], "error": type(exc).__name__})
    return valid, rejected


def prefix_bytes(client, bucket: str, prefix: str) -> int:
    return prefix_evidence(client, bucket, prefix)["bytes"]


def load_bronze_frame(spark: SparkSession, client) -> tuple[DataFrame, dict[str, int]]:
    """Read session Bronze through Spark, never through driver-resident event lists."""

    bucket = os.getenv("MINIO_BRONZE_BUCKET", "cogniflow-bronze")
    inventory = prefix_evidence(client, bucket, "session_events/")
    if not inventory["objects"]:
        return spark.createDataFrame([], SILVER_SCHEMA), {
            "spark_input_bytes": 0,
            "bronze_rows_read": 0,
            "bronze_objects_read": 0,
            "valid_rows": 0,
            "rejected_rows": 0,
        }
    raw = (
        spark.read.schema(BRONZE_SESSION_SCHEMA)
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .json(f"s3a://{bucket}/session_events/")
    )
    event = F.col("event")
    payload = F.col("event.payload")
    valid_condition = (
        F.col("_corrupt_record").isNull()
        & event.event_id.isNotNull()
        & event.session_id.isNotNull()
        & (event.schema_version == "1.0")
        & (event.event_type == "session.snapshot")
        & F.to_timestamp(event.event_time).isNotNull()
        & F.to_timestamp(event.ingested_at).isNotNull()
        & payload.focus_minutes.between(0, 1440)
        & payload.distraction_minutes.between(0, 1440)
        & payload.tasks_due.between(0, 1000)
        & payload.hours_to_deadline.between(0, 87600)
        & F.col("kafka.topic").isNotNull()
        & F.col("kafka.partition").isNotNull()
        & F.col("kafka.offset").isNotNull()
    )
    counts = raw.agg(
        F.count(F.lit(1)).alias("total"),
        F.sum(F.when(valid_condition, 1).otherwise(0)).alias("valid"),
    ).first()
    total = int(counts.total)
    valid_rows = int(counts.valid or 0)
    valid = raw.filter(valid_condition)
    rows = valid.select(
        event.event_id.alias("event_id"),
        event.session_id.alias("session_id"),
        event.user_id.alias("user_id"),
        F.to_timestamp(event.event_time).alias("event_time"),
        F.to_timestamp(event.ingested_at).alias("ingested_at"),
        event.schema_version.alias("schema_version"),
        event.source.alias("source"),
        payload.focus_minutes.alias("focus_minutes"),
        payload.distraction_minutes.alias("distraction_minutes"),
        payload.tasks_due.alias("tasks_due"),
        payload.hours_to_deadline.alias("hours_to_deadline"),
        F.col("kafka.topic").alias("kafka_topic"),
        F.col("kafka.partition").alias("kafka_partition"),
        F.col("kafka.offset").alias("kafka_offset"),
    )
    return rows, {
        "spark_input_bytes": inventory["bytes"],
        "bronze_rows_read": total,
        "bronze_objects_read": inventory["objects"],
        "valid_rows": valid_rows,
        "rejected_rows": total - valid_rows,
    }


def write_evidence(path: str, result: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, target)


def merge_delta(spark: SparkSession, frame: DataFrame, uri: str) -> None:
    if DeltaTable.isDeltaTable(spark, uri):
        DeltaTable.forPath(spark, uri).alias("target").merge(
            frame.alias("source"), "target.event_id = source.event_id"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        frame.write.format("delta").partitionBy("event_date").save(uri)


def add_features(frame: DataFrame) -> DataFrame:
    """Apply the exact Module I ratio semantics with Spark expressions."""

    total = F.col("focus_minutes") + F.col("distraction_minutes")
    return (
        frame.withColumn(
            "focus_ratio", F.when(total == 0, F.lit(0.0)).otherwise(F.col("focus_minutes") / total)
        )
        .withColumn(
            "distraction_ratio",
            F.when(total == 0, F.lit(0.0)).otherwise(F.col("distraction_minutes") / total),
        )
        .withColumn("event_date", F.to_date("event_time"))
        .withColumn("processed_at", F.current_timestamp())
    )


def spark_session() -> SparkSession:
    access = os.environ["MINIO_ROOT_USER"]
    secret = os.environ["MINIO_ROOT_PASSWORD"]
    builder = (
        SparkSession.builder.appName("cogniflow-bronze-to-silver")
        .master("local[1]")
        .config("spark.driver.memory", "1g")
        .config("spark.databricks.delta.snapshotPartitions", "1")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.sql.parquet.compression.codec", "uncompressed")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.hadoop.fs.s3a.endpoint", os.getenv("MINIO_ENDPOINT", "http://minio:9000"))
        .config("spark.hadoop.fs.s3a.access.key", access)
        .config("spark.hadoop.fs.s3a.secret.key", secret)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.sql.session.timeZone", "UTC")
    )
    return builder.getOrCreate()


def main() -> None:
    spark = spark_session()
    spark.sparkContext.setLogLevel("WARN")
    client = s3_client()
    session_rows, accounting = load_bronze_frame(spark, client)
    behavioral_rows, behavioral_rejected = load_behavioral_bronze()
    if not accounting["valid_rows"] and not behavioral_rows:
        raise RuntimeError("No valid Bronze records found")
    if accounting["valid_rows"]:
        frame = add_features(session_rows).dropDuplicates(["event_id"])
        frame = frame.filter(
            F.col("event_time").isNotNull()
            & F.col("focus_ratio").isNotNull()
            & F.col("distraction_ratio").isNotNull()
        ).persist(StorageLevel.DISK_ONLY)
        silver_batch_rows = frame.count()
        try:
            merge_delta(spark, frame, SILVER_URI)
        finally:
            frame.unpersist()
    else:
        silver_batch_rows = 0
    behavioral_count = 0
    if behavioral_rows:
        behavioral = spark.createDataFrame(behavioral_rows, BEHAVIORAL_SCHEMA).dropDuplicates(
            ["event_id", "window_id"]
        ).withColumn("event_date", F.to_date("window_end")).withColumn(
            "processed_at", F.current_timestamp()
        )
        merge_delta(spark, behavioral, BEHAVIORAL_SILVER_URI)
        behavioral_count = spark.read.format("delta").load(BEHAVIORAL_SILVER_URI).count()
    count = spark.read.format("delta").load(SILVER_URI).count() if accounting["valid_rows"] else 0
    history = (DeltaTable.forPath(spark, SILVER_URI).history().select("version", "operation").collect()
               if accounting["valid_rows"] else [])
    result = {
        "schema_version": "1.0",
        "status": "spark_complete",
        **accounting,
        "duplicates_excluded": accounting["valid_rows"] - silver_batch_rows,
        "silver_batch_rows": silver_batch_rows,
        "silver_total_rows": count,
        "delta_physical_bytes": prefix_bytes(client, LAKEHOUSE_BUCKET, "silver/session_features/"),
        "behavioral_silver_rows": behavioral_count,
        "behavioral_rejected_rows": len(behavioral_rejected),
        "history": [row.asDict() for row in history],
    }
    spark.stop()
    if evidence_path := os.getenv("SPARK_EVIDENCE_PATH"):
        write_evidence(evidence_path, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
