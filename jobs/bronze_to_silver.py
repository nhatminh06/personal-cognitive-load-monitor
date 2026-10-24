"""Transform validated Bronze events into an idempotent Delta Silver table."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from delta import configure_spark_with_delta_pip
from delta.tables import DeltaTable
from pyspark.sql import DataFrame, SparkSession, functions as F, types as T

SILVER_URI = "s3a://cogniflow-lakehouse/silver/session_features"
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


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


def load_bronze() -> tuple[list[dict], list[dict]]:
    client = s3_client()
    bucket = os.getenv("MINIO_BRONZE_BUCKET", "cogniflow-bronze")
    valid, rejected = [], []
    listing = client.list_objects_v2(Bucket=bucket, Prefix="session_events/")
    for item in listing.get("Contents", []):
        body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"]
        for line in body.iter_lines():
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
    return valid, rejected


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
    return configure_spark_with_delta_pip(
        builder,
        extra_packages=["org.apache.hadoop:hadoop-aws:3.3.4"],
    ).getOrCreate()


def main() -> None:
    spark = spark_session()
    rows, rejected = load_bronze()
    if not rows:
        raise RuntimeError("No valid Bronze records found")
    frame = add_features(spark.createDataFrame(rows, SILVER_SCHEMA)).dropDuplicates(["event_id"])
    frame = frame.filter(
        F.col("event_time").isNotNull()
        & F.col("focus_ratio").isNotNull()
        & F.col("distraction_ratio").isNotNull()
    )
    if DeltaTable.isDeltaTable(spark, SILVER_URI):
        target = DeltaTable.forPath(spark, SILVER_URI)
        target.alias("target").merge(
            frame.alias("source"), "target.event_id = source.event_id"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        frame.write.format("delta").partitionBy("event_date").save(SILVER_URI)
    count = spark.read.format("delta").load(SILVER_URI).count()
    history = DeltaTable.forPath(spark, SILVER_URI).history().select("version", "operation").collect()
    print(json.dumps({"silver_rows": count, "rejected_rows": len(rejected), "history": [row.asDict() for row in history]}))
    spark.stop()


if __name__ == "__main__":
    main()
