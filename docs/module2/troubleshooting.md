# Troubleshooting

- Compose dependency error: enable every required profile, for example `--profile lake --profile analytics`.
- Trino cannot rename S3 directories: use the keyed incremental models; do not change Gold back to dbt's default table replacement.
- Flink JSON linkage error: rebuild the supplied image; its Jackson dependencies are version-pinned and shaded.
- Missing online features: confirm the Flink REST job is `RUNNING`, inspect Redis TTL, and check the feature timestamp against `ONLINE_FEATURE_MAX_AGE_SECONDS`.
- Low memory: `make module2-stop`, then start only the profile under test. Persistent volumes are intentionally retained.
