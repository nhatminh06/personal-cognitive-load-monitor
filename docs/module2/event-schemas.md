# Event schemas

The authoritative JSON Schema is `docs/module2/schemas/session-event-v1.json`, generated from `SessionEvent` with:

```bash
uv run python scripts/export_event_schema.py
```

`schema_version=1.0` carries one `session.snapshot` with a UUID event ID, session-ordering key, optional pseudonymous subject, timezone-aware event/ingestion timestamps, source, provenance and the unchanged Module I measurements. Unknown fields are rejected. Raw names, email addresses and device identifiers are intentionally absent.

Evolution creates a new schema version and topic when a breaking change is required. Consumers must validate known versions and quarantine unknown versions rather than guessing.
