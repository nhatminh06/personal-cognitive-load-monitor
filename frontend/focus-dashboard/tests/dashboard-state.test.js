import test from 'node:test';
import assert from 'node:assert/strict';
import {
  effectiveLabels, effortBand, eventDescription, legalActions, mergeTimeline,
  presentationClock, windowAvailability,
} from '../../../src/preprocessing_api/static/focus/dashboard-state.js';

test('legal controls follow the server lifecycle', () => {
  assert.deepEqual(legalActions('session.started'), ['pause', 'complete']);
  assert.deepEqual(legalActions('session.resumed'), ['pause', 'complete']);
  assert.deepEqual(legalActions('session.paused'), ['resume', 'complete']);
  assert.deepEqual(legalActions('session.completed'), []);
});

test('rating corrections remain distinct from predictions', () => {
  assert.equal(effortBand(1), 'LOW'); assert.equal(effortBand(5), 'MEDIUM'); assert.equal(effortBand(7), 'HIGH');
  const initial = { event_type: 'effort.reported', window_id: 'w1', label_id: 'l1', effort_rating: 6, reported_at: '2026-01-01T00:06:00Z' };
  const correction = { ...initial, label_id: 'l2', effort_rating: 4, supersedes_label_id: 'l1', reported_at: '2026-01-01T00:07:00Z' };
  assert.equal(effectiveLabels([correction, initial]).get('w1').label_id, 'l2');
  assert.match(eventDescription(correction), /Self-reported effort/);
});

test('missing aggregate data remains missing instead of zero', () => {
  assert.deepEqual(windowAvailability([], 'w1'), { activity: undefined, cv: undefined });
  const unavailable = { event_type: 'cv.window', window_id: 'w1', camera_available: false };
  assert.equal(windowAvailability([unavailable], 'w1').cv.camera_available, false);
  assert.match(eventDescription(unavailable), /unavailable/);
});

test('presentation timer does not manufacture windows while paused', () => {
  const start = '2026-01-01T00:00:00Z';
  assert.deepEqual(presentationClock('session.paused', start, Date.parse(start) + 360000, 120), { elapsedSeconds: 120, windowSeconds: 0 });
  assert.deepEqual(presentationClock('session.started', start, Date.parse(start) + 301000, 120), { elapsedSeconds: 421, windowSeconds: 1 });
});

test('timeline pagination merge is chronological and idempotent', () => {
  const later = { event_id: '2', event_type: 'session.paused', event_time: '2026-01-01T00:06:00Z' };
  const earlier = { event_id: '1', event_type: 'session.started', event_time: '2026-01-01T00:00:00Z' };
  assert.deepEqual(mergeTimeline([later, earlier, later]).map((item) => item.event_id), ['1', '2']);
});
