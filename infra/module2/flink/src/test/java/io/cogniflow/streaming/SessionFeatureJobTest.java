package io.cogniflow.streaming;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.InputStream;
import org.junit.jupiter.api.Test;

final class SessionFeatureJobTest {
  @Test void sharedFixturesMatchTheSixFeatureContract() throws Exception {
    try (InputStream stream = getClass().getResourceAsStream("/feature_vectors.json")) {
      JsonNode cases = SessionFeatureJob.JSON.readTree(stream);
      for (JsonNode item : cases) {
        JsonNode input = item.path("input");
        long focus = input.path("focus_minutes").asLong();
        long distraction = input.path("distraction_minutes").asLong();
        long total = focus + distraction;
        double[] actual = {focus, distraction, input.path("tasks_due").asLong(),
            input.path("hours_to_deadline").asDouble(),
            total == 0 ? 0 : (double) focus / total,
            total == 0 ? 0 : (double) distraction / total};
        for (int index = 0; index < actual.length; index++) {
          assertEquals(item.path("expected").get(index).asDouble(), actual[index], 1e-12);
        }
        assertEquals("1.0", item.path("feature_schema_version").asText());
      }
    }
  }

  @Test void aggregateUsesSumsAndLatestSnapshotFields() {
    SessionFeatureJob.FeatureAggregate aggregate = new SessionFeatureJob.FeatureAggregate();
    var value = aggregate.add(new SessionFeatureJob.Event("a", "s", 1000, 30, 10, 2, 8),
        aggregate.createAccumulator());
    value = aggregate.add(new SessionFeatureJob.Event("b", "s", 2000, 20, 20, 5, 3), value);
    assertEquals(50, value.focus()); assertEquals(30, value.distraction());
    assertEquals(5, value.tasksDue()); assertEquals(3, value.hoursToDeadline());
    assertEquals(2, value.count()); assertEquals(2000, value.latestEventTime());
  }

  @Test void invalidTimestampAndSchemaFailClosed() {
    assertThrows(IllegalArgumentException.class, () -> SessionFeatureJob.eventTime("{\"event_time\":\"bad\"}"));
    assertThrows(IllegalArgumentException.class, () -> SessionFeatureJob.parse(
        "{\"schema_version\":\"2.0\",\"event_type\":\"session.snapshot\"}"));
    String invalid = "{\"schema_version\":\"1.0\",\"event_type\":\"session.snapshot\","
        + "\"event_id\":\"5f7dcb40-15bf-4d40-9342-bcf0c6b3e94b\",\"session_id\":\"s\","
        + "\"event_time\":\"2026-10-24T00:00:00Z\",\"payload\":{\"focus_minutes\":-1,"
        + "\"distraction_minutes\":0,\"tasks_due\":0,\"hours_to_deadline\":1}}";
    assertThrows(IllegalArgumentException.class, () -> SessionFeatureJob.parse(invalid));
  }

  @Test void invalidEventQuarantineDoesNotCopyRawPayload() throws Exception {
    String raw = "secret malformed payload";
    String quarantine = SessionFeatureJob.invalidEventJson(raw, new IllegalArgumentException());
    JsonNode value = SessionFeatureJob.JSON.readTree(quarantine);
    assertEquals(raw.length(), value.path("raw_size_bytes").asInt());
    assertEquals(64, value.path("raw_sha256").asText().length());
    assertEquals(false, quarantine.contains(raw));
  }
}
