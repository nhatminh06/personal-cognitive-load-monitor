// Synthetic payloads follow the existing Worker contract: no lifecycle sequence field.
export function observation(n, type = 'behavioral.window', session = 'synthetic-session') {
  const id = x => `00000000-0000-4000-8000-${String(x).padStart(12, '0')}`;
  const stamp = Date.parse('2026-11-26T00:00:01Z') + (n - 10) * 300000;
  const iso = ms => new Date(ms).toISOString().replace('.000Z', '+00:00');
  const start = iso(stamp), end = iso(stamp + 300000);
  return {
    schema_version: '1.0', event_id: id(n), idempotency_key: `synthetic-${n}`,
    session_id: session, subject_id: null, source: 'synthetic', producer_version: 'g1b3',
    event_type: type, event_time: end, ingested_at: end, window_id: id(n + 1000),
    window_start: start, window_end: end, feature_cutoff: end,
    ...(type === 'effort.reported' ? {
      label_id: id(n + 2000), effort_rating: 4, reported_at: end,
      label_source: 'user_self_report', confidence: null, supersedes_label_id: null,
    } : { active_seconds: 200, idle_seconds: 100, keyboard_event_count: 1,
      pointer_event_count: 1, application_switch_count: 0, build_count: null, test_count: null }),
  };
}
