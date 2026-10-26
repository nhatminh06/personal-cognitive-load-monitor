# Flink and Redis

The Flink 1.20.5 Java DataStream job consumes versioned session events with configurable bounded-out-of-order watermarks (`FLINK_OUT_OF_ORDER_SECONDS`, default 120). It uses checkpointed, 24-hour TTL event-ID state for duplicate suppression. Sliding event-time windows (`FLINK_WINDOW_SECONDS`, default 300; `FLINK_SLIDE_SECONDS`, default 60) and tumbling windows produce summed focus/distraction minutes, latest-snapshot task/deadline values, exact ratio semantics, event counts and window bounds. `FLINK_ALLOWED_LATENESS_SECONDS` defaults to 30; later records are explicitly quarantined to `cogniflow.dead-letter.v1`.

Only rolling updates enter Redis; both window types enter `cogniflow.features.v1`. A Redis Lua compare-and-set rejects an update whose ISO-8601 UTC feature timestamp is older than the stored value. `GET /features/{session_id}` remains fail-closed and `/predict` is unchanged.

Runtime evidence on 2026-10-24 used 15 deterministic source events plus three injected duplicates. For `[15:00:00,15:00:10)`, Flink and the fixture oracle both returned 11 unique events, 693 focus minutes, 512 distraction minutes and ratios `0.575103734439834/0.42489626556016596`. Restarting the TaskManager restored checkpoint 8 and all six operators returned to `RUNNING`. A stale Redis write returned `0` and did not replace the `15:00:09Z` feature.
