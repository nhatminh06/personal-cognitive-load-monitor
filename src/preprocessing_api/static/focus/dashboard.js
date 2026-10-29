import {
  ACTIVE_STATES, TERMINAL_STATES, effectiveLabels, effortBand, eventDescription,
  eventName, formatDuration, legalActions, mergeTimeline, presentationClock,
  windowAvailability,
} from './dashboard-state.js';

const PAGE_SIZE = 50;
const REQUEST_TIMEOUT_MS = 8000;
const SESSION_STORAGE_KEY = 'cogniflow.focus.session-id';

/** @typedef {{session_id:string,session_kind:'programming'|'study',privacy_mode:'behavioral'|'behavioral_cv',planned_duration_seconds:number|null,state:import('./dashboard-state.js').SessionState,last_sequence:number,last_event_time:string,confirmed_active_seconds:number,completed_windows:Array<{window_id:string,window_start:string,window_end:string}>}} Session */

/** @type {string|null} */ let apiKey = null;
/** @type {Session|null} */ let session = null;
/** @type {Array<Record<string, unknown>>} */ let timeline = [];
let timelineTotal = 0;
let timelineOffset = 0;
let refreshFailed = false;
/** @type {Set<AbortController>} */ const activeRequests = new Set();
/** @type {number|null} */ let pollTimer = null;
/** @type {Map<string, Record<string, unknown>>} */ const pendingPayloads = new Map();
/** @type {HTMLButtonElement|null} */ let dialogInvoker = null;

/** @template {typeof Element} T @param {string} selector @param {T} constructor @returns {InstanceType<T>} */
function required(selector, constructor) {
  const element = document.querySelector(selector);
  if (!(element instanceof constructor)) throw new Error(`Missing dashboard element: ${selector}`);
  // @ts-ignore - runtime constructor check establishes the concrete DOM type
  return element;
}

const elements = {
  credentialView: required('#credential-view', HTMLElement), credentialForm: required('#credential-form', HTMLFormElement),
  credentialInput: required('#api-key', HTMLInputElement), credentialError: required('#credential-error', HTMLElement),
  appView: required('#app-view', HTMLElement), setupView: required('#setup-view', HTMLElement), setupForm: required('#setup-form', HTMLFormElement),
  sessionView: required('#session-view', HTMLElement), sessionTitle: required('#session-title', HTMLElement),
  disconnect: required('#disconnect', HTMLButtonElement), status: required('#status-message', HTMLElement), error: required('#error-message', HTMLElement),
  stateBadge: required('#state-badge', HTMLElement), elapsed: required('#elapsed', HTMLElement), windowTime: required('#window-time', HTMLElement),
  windowProgress: required('#window-progress', HTMLProgressElement), windowLabel: required('#window-label', HTMLElement), sessionKind: required('#session-kind', HTMLElement),
  sessionStart: required('#session-start', HTMLElement), privacyMode: required('#privacy-mode', HTMLElement),
  controls: required('#session-controls', HTMLElement), availability: required('#availability-content', HTMLElement),
  cameraStatus: required('#camera-status', HTMLElement), effortCopy: required('#effort-copy', HTMLElement),
  effortForm: required('#effort-form', HTMLFormElement), effortWindow: required('#effort-window', HTMLSelectElement), saveRating: required('#save-rating', HTMLButtonElement),
  timeline: required('#timeline', HTMLOListElement), timelineEmpty: required('#timeline-empty', HTMLElement),
  timelineCount: required('#timeline-count', HTMLElement), loadEarlier: required('#load-earlier', HTMLButtonElement),
  refresh: required('#refresh', HTMLButtonElement), dialog: required('#confirm-dialog', HTMLDialogElement),
  dialogTitle: required('#dialog-title', HTMLElement), dialogCopy: required('#dialog-copy', HTMLElement),
  dialogConfirm: required('#dialog-confirm', HTMLButtonElement),
};

function uuid() { return crypto.randomUUID(); }
function isoNow() { return new Date().toISOString(); }
/** @param {string|number|Date} value */
function localTime(value) { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)); }
/** @param {string} value */
function stateLabel(value) { return value.replace('session.', ''); }
function clearMessage() { elements.error.textContent = ''; elements.status.textContent = ''; }
/** @param {string} message */ function announce(message) { elements.status.textContent = message; }
/** @param {string} message */ function fail(message) {
  if (!elements.credentialView.hidden) {
    elements.credentialError.textContent = message; elements.credentialError.focus(); return;
  }
  elements.error.textContent = message; elements.error.focus();
}

/** @param {number} status @param {string} detail */
function userError(status, detail) {
  if (status === 401) return 'Authentication failed. Re-enter the local API key.';
  if (status === 404) return 'This session is unavailable for this credential.';
  if (status === 409) return 'The server state changed. The session has been refreshed.';
  if (status === 422 && detail.includes('future')) return 'Your device clock is ahead of the server. Check the clock and try again.';
  if (status === 422) return 'The request did not match the session contract.';
  if (status === 503) return 'The local CogniFlow service is unavailable. Try again shortly.';
  return 'The request could not be completed.';
}

/** @param {string} path @param {RequestInit} [options] */
async function api(path, options = {}) {
  if (!apiKey) throw new Error('Not connected');
  const controller = new AbortController(); activeRequests.add(controller);
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      ...options, signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey, ...(options.headers || {}) },
    });
    let body = null;
    try { body = await response.json(); } catch { body = null; }
    if (!response.ok) {
      const detail = typeof body?.detail === 'string' ? body.detail : '';
      const error = new Error(userError(response.status, detail));
      // @ts-ignore - local typed error metadata
      error.status = response.status;
      if (response.status === 401) disconnect();
      throw error;
    }
    return body;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('The local service did not respond in time.');
    throw error;
  } finally {
    window.clearTimeout(timeout);
    activeRequests.delete(controller);
  }
}

/** @param {string} key @param {() => Record<string, unknown>} create @param {string} path */
async function mutate(key, create, path) {
  const payload = pendingPayloads.get(key) || create(); pendingPayloads.set(key, payload);
  const result = await api(path, { method: 'POST', body: JSON.stringify(payload) });
  pendingPayloads.delete(key);
  return result;
}

/** @param {string} sessionId @param {string} eventType */
function commonEvent(sessionId, eventType) {
  const now = isoNow();
  return { schema_version: '1.0', event_id: uuid(), session_id: sessionId, event_time: now,
    ingested_at: now, source: 'focus_dashboard', producer_version: '1.0.0',
    idempotency_key: `dashboard:${eventType}:${uuid()}` };
}

function disconnect() {
  activeRequests.forEach((controller) => controller.abort()); activeRequests.clear();
  apiKey = null; session = null; timeline = []; pendingPayloads.clear();
  if (pollTimer !== null) window.clearInterval(pollTimer); pollTimer = null;
  elements.credentialForm.reset(); elements.appView.hidden = true; elements.credentialView.hidden = false;
  elements.sessionView.hidden = true; elements.setupView.hidden = false; clearMessage();
  elements.credentialInput.focus();
}

/** @param {string} key */ async function connect(key) {
  apiKey = key; elements.credentialInput.value = ''; clearMessage();
  elements.credentialView.hidden = true; elements.appView.hidden = false;
  await api('/sessions/auth-check');
  const stored = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!stored) { elements.setupView.hidden = false; elements.sessionView.hidden = true; announce('Connected locally.'); return; }
  try { await loadSession(stored); announce('Persisted session restored after authentication.'); }
  catch (error) {
    localStorage.removeItem(SESSION_STORAGE_KEY); session = null; timeline = [];
    elements.setupView.hidden = false; elements.sessionView.hidden = true;
    if (error instanceof Error) fail(error.message);
  }
}

/** @param {FormData} form */ async function startSession(form) {
  const kind = String(form.get('session-kind'));
  const privacy = String(form.get('privacy-mode'));
  const planned = String(form.get('planned-duration') || '');
  const sessionId = `local-${uuid()}`;
  const payload = { ...commonEvent(sessionId, 'start'), event_type: 'session.started', sequence: 1,
    session_kind: kind, privacy_mode: privacy,
    planned_duration_seconds: planned ? Number(planned) * 60 : null };
  session = await mutate('start', () => payload, '/sessions');
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  await loadSession(sessionId); announce('Session started.'); elements.sessionTitle.focus();
}

/** @param {string} sessionId */ async function loadSession(sessionId) {
  session = await api(`/sessions/${encodeURIComponent(sessionId)}`);
  await loadTimelineTail(); render(); startPolling();
}

async function refreshAll({ materialize = true } = {}) {
  if (!session) return;
  const path = `/sessions/${encodeURIComponent(session.session_id)}`;
  if (materialize && ACTIVE_STATES.has(session.state)) session = await api(`${path}/windows/refresh`, { method: 'POST' });
  else session = await api(path);
  await loadTimelineTail(); render();
}

async function backgroundRefresh() {
  try {
    await refreshAll();
    if (refreshFailed) announce('Connection restored. State is confirmed by the server.');
    refreshFailed = false;
  } catch {
    if (!refreshFailed) announce('Refresh failed—showing the last server-confirmed state.');
    refreshFailed = true;
  }
}

async function loadTimelineTail() {
  if (!session) return;
  const base = `/sessions/${encodeURIComponent(session.session_id)}/timeline`;
  const first = await api(`${base}?limit=1&offset=0`); timelineTotal = Number(first.total);
  timelineOffset = Math.max(0, timelineTotal - PAGE_SIZE);
  const page = await api(`${base}?limit=${PAGE_SIZE}&offset=${timelineOffset}`);
  timeline = mergeTimeline(page.items); timelineTotal = Number(page.total);
}

async function loadEarlier() {
  if (!session || timelineOffset === 0) return;
  const nextOffset = Math.max(0, timelineOffset - PAGE_SIZE);
  const limit = timelineOffset - nextOffset;
  const page = await api(`/sessions/${encodeURIComponent(session.session_id)}/timeline?limit=${limit}&offset=${nextOffset}`);
  timeline = mergeTimeline([...page.items, ...timeline]); timelineOffset = nextOffset; renderTimeline();
}

function startPolling() {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = window.setInterval(() => {
    if (!document.hidden && session && !TERMINAL_STATES.has(session.state)) backgroundRefresh();
  }, 30000);
}

/** @param {'pause'|'resume'|'complete'} action */ async function transition(action) {
  if (!session) return;
  const type = { pause: 'session.paused', resume: 'session.resumed', complete: 'session.completed' }[action];
  const sessionId = session.session_id;
  const payload = { ...commonEvent(sessionId, action), event_type: type,
    sequence: session.last_sequence + 1, session_kind: session.session_kind,
    privacy_mode: session.privacy_mode, planned_duration_seconds: session.planned_duration_seconds };
  try {
    await mutate(`transition:${session.last_sequence}:${action}`, () => payload,
      `/sessions/${encodeURIComponent(sessionId)}/transitions`);
    await refreshAll({ materialize: false });
    announce(action === 'pause' ? 'Session paused. The incomplete active window was discarded.' : `Session ${type.replace('session.', '')}.`);
    elements.sessionTitle.focus();
  } catch (error) {
    // @ts-ignore - local typed error metadata
    if (error?.status === 409) await refreshAll({ materialize: false });
    throw error;
  }
}

/** @param {'pause'|'complete'} action @param {HTMLButtonElement} invoker */
function confirmTransition(action, invoker) {
  dialogInvoker = invoker; elements.dialogTitle.textContent = action === 'pause' ? 'Pause this session?' : 'Complete this session?';
  elements.dialogCopy.textContent = action === 'pause'
    ? 'Pausing ends this active segment. Any incomplete five-minute window will not be saved.'
    : 'Completion ends this session. Persisted windows and ratings remain available for review.';
  elements.dialogConfirm.textContent = action === 'pause' ? 'Pause session' : 'Complete session';
  elements.dialogConfirm.dataset.action = action; elements.dialog.returnValue = '';
  elements.dialog.showModal(); elements.dialogConfirm.focus();
}

/** @param {FormData} form */ async function saveEffort(form) {
  if (!session || !session.completed_windows.length) return;
  const windowId = String(form.get('effort-window') || '');
  const selected = session.completed_windows.find((item) => item.window_id === windowId);
  const rating = Number(form.get('effort'));
  if (!selected) throw new Error('Choose a completed window.');
  if (!rating) throw new Error('Choose an effort rating from 1 through 7.');
  const existing = effectiveLabels(timeline).get(selected.window_id); const now = isoNow();
  const payload = { ...commonEvent(session.session_id, 'effort'), event_time: now, ingested_at: now,
    event_type: 'effort.reported', label_id: uuid(), window_id: selected.window_id,
    window_start: selected.window_start, window_end: selected.window_end, feature_cutoff: selected.window_end,
    effort_rating: rating, reported_at: now, label_source: 'user_self_report', confidence: null,
    supersedes_label_id: existing?.label_id || null };
  await mutate(`label:${selected.window_id}:${existing?.label_id || 'initial'}`, () => payload,
    `/sessions/${encodeURIComponent(session.session_id)}/labels`);
  await refreshAll({ materialize: false }); announce(existing ? 'Your correction was saved.' : 'Your rating was saved.');
}

function render() {
  if (!session) return;
  elements.setupView.hidden = true; elements.sessionView.hidden = false;
  elements.sessionTitle.textContent = `${session.session_kind === 'study' ? 'Study' : 'Programming'} session`;
  elements.stateBadge.textContent = stateLabel(session.state); elements.sessionKind.textContent = session.session_kind;
  elements.privacyMode.textContent = session.privacy_mode === 'behavioral_cv' ? 'Behavioral + optional CV' : 'Behavioral only';
  const start = timeline.find((item) => item.event_type === 'session.started');
  elements.sessionStart.textContent = start ? localTime(String(start.event_time)) : localTime(session.last_event_time);
  renderControls(); renderEffort(); renderAvailability(); renderTimeline(); tick();
}

function renderControls() {
  const current = session;
  if (!current) return;
  elements.controls.replaceChildren();
  for (const action of legalActions(current.state)) {
    const button = document.createElement('button'); button.type = 'button'; button.className = `button ${action === 'complete' ? 'secondary' : 'primary'}`;
    button.textContent = action[0].toUpperCase() + action.slice(1); button.addEventListener('click', () => {
      if (action === 'pause' || action === 'complete') confirmTransition(action, button);
      else runBusy(button, () => transition(action));
    }); elements.controls.append(button);
  }
}

function renderAvailability() {
  const current = session;
  if (!current) return;
  elements.availability.replaceChildren();
  const selected = selectedWindow();
  if (!selected) { elements.availability.textContent = 'No completed five-minute windows yet.'; return; }
  const { activity, cv } = windowAvailability(timeline, selected.window_id);
  const label = effectiveLabels(timeline).get(selected.window_id);
  const list = document.createElement('dl'); list.className = 'availability-list';
  const facts = [
    ['Window', `${localTime(selected.window_start)} – ${new Date(selected.window_end).toLocaleTimeString()}`],
    ['Behavioral', activity ? 'Aggregate received' : 'No aggregate received'],
    ['Active / idle', activity ? `${activity.active_seconds}s / ${activity.idle_seconds}s` : 'Unavailable'],
    ['Keyboard / pointer', activity ? `${activity.keyboard_event_count} / ${activity.pointer_event_count}` : 'Unavailable'],
    ['App switches', activity ? String(activity.application_switch_count) : 'Unavailable'],
    ['Builds / tests', activity ? `${activity.build_count ?? 'Unavailable'} / ${activity.test_count ?? 'Unavailable'}` : 'Unavailable'],
    ['CV', !cv ? 'No aggregate received' : cv.camera_available === false ? 'Measurement unavailable' : 'Aggregate recorded'],
    ['Your rating', label ? `${label.effort_rating} · ${effortBand(Number(label.effort_rating))}` : 'Not submitted'],
  ];
  for (const [term, value] of facts) { const row = document.createElement('div'); const dt = document.createElement('dt'); const dd = document.createElement('dd'); dt.textContent = term; dd.textContent = value; row.append(dt, dd); list.append(row); }
  elements.availability.append(list);
  elements.cameraStatus.textContent = current.privacy_mode !== 'behavioral_cv' ? 'Camera collection is off.'
    : `Optional collector control is separate. Selected window: ${!cv ? 'no CV aggregate' : cv.camera_available === false ? 'measurement unavailable' : 'aggregate recorded'}.`;
}

function selectedWindow() {
  const current = session;
  if (!current) return undefined;
  return current.completed_windows.find((item) => item.window_id === elements.effortWindow.value)
    || current.completed_windows.at(-1);
}

function renderEffort() {
  const current = session;
  if (!current) return;
  const previous = elements.effortWindow.value;
  const labels = effectiveLabels(timeline); elements.effortWindow.replaceChildren();
  for (const item of current.completed_windows) {
    const option = document.createElement('option'); option.value = item.window_id;
    option.textContent = `Ending ${localTime(item.window_end)}${labels.has(item.window_id) ? ' · rated' : ' · unrated'}`;
    elements.effortWindow.append(option);
  }
  const preferred = current.completed_windows.some((item) => item.window_id === previous) ? previous
    : current.completed_windows.find((item) => !labels.has(item.window_id))?.window_id || current.completed_windows.at(-1)?.window_id;
  if (preferred) elements.effortWindow.value = preferred;
  const selected = selectedWindow(); elements.effortForm.hidden = !selected;
  if (!selected) { elements.effortCopy.textContent = 'Rating becomes available after a completed five-minute window.'; return; }
  const label = labels.get(selected.window_id);
  elements.effortCopy.textContent = label
    ? `Saved rating ${label.effort_rating} (${effortBand(Number(label.effort_rating))}). Corrections append to history.`
    : `Window ending ${localTime(selected.window_end)} is ready for your rating.`;
  elements.saveRating.textContent = label ? 'Save correction' : 'Save my rating';
  elements.effortForm.querySelectorAll('input[name="effort"]').forEach((input) => { if (input instanceof HTMLInputElement) input.checked = false; });
  if (label) { const radio = elements.effortForm.querySelector(`input[value="${label.effort_rating}"]`); if (radio instanceof HTMLInputElement) radio.checked = true; }
}

function renderTimeline() {
  elements.timeline.replaceChildren(); elements.timelineEmpty.hidden = timeline.length > 0;
  for (const item of timeline) {
    const li = document.createElement('li'); const time = document.createElement('time'); const name = document.createElement('strong'); const detail = document.createElement('div'); const copy = document.createElement('p'); const technical = document.createElement('p');
    time.dateTime = String(item.event_time); time.textContent = localTime(String(item.event_time)); time.title = String(item.event_time);
    name.textContent = eventName(item); copy.textContent = eventDescription(item);
    technical.className = 'technical'; technical.textContent = item.window_id ? `Window ${item.window_id}` : `Event ${item.event_id || 'server-generated'}`;
    detail.append(copy, technical); li.append(time, name, detail); elements.timeline.append(li);
  }
  elements.loadEarlier.hidden = timelineOffset === 0; elements.timelineCount.textContent = `${timeline.length} of ${timelineTotal} persisted events loaded.`;
}

function tick() {
  if (!session) return;
  const clock = presentationClock(session.state, session.last_event_time, Date.now(), session.confirmed_active_seconds);
  elements.elapsed.textContent = formatDuration(clock.elapsedSeconds); elements.windowProgress.value = clock.windowSeconds;
  const active = ACTIVE_STATES.has(session.state);
  elements.windowLabel.textContent = active ? 'Current active window' : session.state === 'session.paused' ? 'No active window while paused' : 'Session ended';
  elements.windowTime.textContent = active ? `${Math.floor(clock.windowSeconds / 60)}:${String(clock.windowSeconds % 60).padStart(2, '0')} / 5:00` : '—';
}

/** @param {HTMLButtonElement|HTMLFormElement} control @param {() => Promise<void>} task */
async function runBusy(control, task) {
  clearMessage(); control.setAttribute('aria-busy', 'true');
  const buttons = control.matches('form') ? control.querySelectorAll('button') : [control]; buttons.forEach((button) => { button.disabled = true; });
  try { await task(); }
  catch (error) { fail(error instanceof Error ? error.message : 'The request could not be completed.'); }
  finally { control.removeAttribute('aria-busy'); buttons.forEach((button) => { button.disabled = false; }); }
}

elements.credentialForm.addEventListener('submit', (event) => { event.preventDefault(); const form = new FormData(elements.credentialForm); const key = String(form.get('api-key') || ''); if (!key.trim()) { elements.credentialError.textContent = 'Enter the local API key.'; elements.credentialInput.focus(); return; } elements.credentialError.textContent = ''; runBusy(elements.credentialForm, () => connect(key)); });
elements.setupForm.addEventListener('submit', (event) => { event.preventDefault(); runBusy(elements.setupForm, () => startSession(new FormData(elements.setupForm))); });
elements.effortForm.addEventListener('submit', (event) => { event.preventDefault(); runBusy(elements.effortForm, () => saveEffort(new FormData(elements.effortForm))); });
elements.effortWindow.addEventListener('change', () => { renderEffort(); renderAvailability(); });
elements.disconnect.addEventListener('click', disconnect);
elements.refresh.addEventListener('click', () => runBusy(elements.refresh, async () => { await refreshAll(); announce('Session refreshed from the server.'); }));
elements.loadEarlier.addEventListener('click', () => runBusy(elements.loadEarlier, loadEarlier));
elements.dialog.addEventListener('keydown', (event) => {
  if (event.key !== 'Tab') return;
  const buttons = [...elements.dialog.querySelectorAll('button:not(:disabled)')];
  const first = buttons[0]; const last = buttons.at(-1);
  if (!(first instanceof HTMLButtonElement) || !(last instanceof HTMLButtonElement)) return;
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
elements.dialog.addEventListener('close', () => { if (elements.dialog.returnValue === 'confirm') { const action = elements.dialogConfirm.dataset.action; const button = dialogInvoker; if ((action === 'pause' || action === 'complete') && button) runBusy(button, () => transition(action)); } dialogInvoker?.focus(); dialogInvoker = null; });
document.addEventListener('visibilitychange', () => { if (!document.hidden && session) backgroundRefresh(); });
window.addEventListener('beforeunload', () => activeRequests.forEach((controller) => controller.abort()));
window.setInterval(tick, 1000);
