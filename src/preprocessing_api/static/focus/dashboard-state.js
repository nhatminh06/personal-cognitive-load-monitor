/** @typedef {'session.started'|'session.paused'|'session.resumed'|'session.completed'|'session.cancelled'} SessionState */

export const ACTIVE_STATES = new Set(['session.started', 'session.resumed']);
export const TERMINAL_STATES = new Set(['session.completed', 'session.cancelled']);

/** @param {SessionState} state @returns {Array<'pause'|'resume'|'complete'>} */
export function legalActions(state) {
  if (ACTIVE_STATES.has(state)) return ['pause', 'complete'];
  if (state === 'session.paused') return ['resume', 'complete'];
  return [];
}

/** @param {number} rating */
export function effortBand(rating) {
  if (!Number.isInteger(rating) || rating < 1 || rating > 7) throw new Error('Invalid effort rating');
  if (rating <= 2) return 'LOW';
  if (rating <= 5) return 'MEDIUM';
  return 'HIGH';
}

/** @param {Array<Record<string, unknown>>} items */
export function effectiveLabels(items) {
  /** @type {Map<string, Record<string, unknown>>} */
  const labels = new Map();
  for (const item of items) {
    if (item.event_type !== 'effort.reported' || typeof item.window_id !== 'string') continue;
    const current = labels.get(item.window_id);
    if (!current || String(item.reported_at) >= String(current.reported_at)) labels.set(item.window_id, item);
  }
  return labels;
}

/** @param {Array<Record<string, unknown>>} items @param {string} windowId */
export function windowAvailability(items, windowId) {
  const activity = items.find((item) => item.event_type === 'behavioral.window' && item.window_id === windowId);
  const cv = items.find((item) => item.event_type === 'cv.window' && item.window_id === windowId);
  return { activity, cv };
}

/** @param {SessionState} state @param {string} segmentStart @param {number} nowMs @param {number} confirmedSeconds */
export function presentationClock(state, segmentStart, nowMs, confirmedSeconds = 0) {
  const segmentSeconds = ACTIVE_STATES.has(state)
    ? Math.max(0, Math.floor((nowMs - Date.parse(segmentStart)) / 1000)) : 0;
  return { elapsedSeconds: confirmedSeconds + segmentSeconds,
    windowSeconds: ACTIVE_STATES.has(state) ? segmentSeconds % 300 : 0 };
}

/** @param {number} seconds */
export function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return [hours, minutes, remainder].map((value) => String(value).padStart(2, '0')).join(':');
}

/** @param {Record<string, unknown>} item */
export function eventDescription(item) {
  switch (item.event_type) {
    case 'session.started': return 'Session started.';
    case 'session.paused': return 'Session paused. Any incomplete active window was discarded.';
    case 'session.resumed': return 'Session resumed with a new active window.';
    case 'session.completed': return 'Session completed.';
    case 'session.cancelled': return 'Session cancelled.';
    case 'window.completed': return 'Five-minute window confirmed by the server.';
    case 'behavioral.window': return 'Behavioral aggregate received.';
    case 'cv.window': return item.camera_available === false ? 'CV measurement unavailable.' : 'Aggregate CV measurement received.';
    case 'effort.reported': return `Self-reported effort saved: ${item.effort_rating} (${effortBand(Number(item.effort_rating))}).`;
    default: return 'Persisted session event.';
  }
}

/** @param {Record<string, unknown>} item */
export function eventName(item) {
  /** @type {Record<string, string>} */
  const names = {
    'session.started': 'Started', 'session.paused': 'Paused', 'session.resumed': 'Resumed',
    'session.completed': 'Completed', 'session.cancelled': 'Cancelled',
    'window.completed': 'Window complete', 'behavioral.window': 'Behavioral data',
    'cv.window': 'CV availability', 'effort.reported': item.supersedes_label_id ? 'Rating corrected' : 'Rating reported',
  };
  return names[String(item.event_type)] || 'Session event';
}

/** @param {Array<Record<string, unknown>>} items */
export function mergeTimeline(items) {
  const byIdentity = new Map();
  for (const item of items) {
    const key = String(item.event_id || `${item.event_type}:${item.window_id || ''}:${item.event_time}`);
    byIdentity.set(key, item);
  }
  return [...byIdentity.values()].sort((left, right) => String(left.event_time).localeCompare(String(right.event_time)));
}
