import assert from 'node:assert/strict';
import { observation } from '../g1b-outbox/fixtures.mjs';
import { createHash, createHmac, randomBytes, randomUUID } from 'node:crypto';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { append } from '../g1b-outbox/outbox.mjs';
import { startGateway } from './gateway.mjs';
import { dispatchBatch, inspectDead, reconcile } from './dispatcher.mjs';

const event = (n, sequence = 1, session = `synthetic-session-${n}`) => ({
  schema_version: '1.0', event_id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  idempotency_key: `synthetic-${n}`, session_id: session, subject_id: null,
  source: 'synthetic', producer_version: 'g1b2',
  event_type: sequence === 1 ? 'session.started' : 'session.paused', sequence,
  session_kind: 'study', privacy_mode: 'behavioral',
  event_time: `2026-11-26T00:00:0${sequence}+00:00`,
  ingested_at: `2026-11-26T00:00:0${sequence}+00:00`,
});
const first = (db, sql, ...args) => db.prepare(sql).bind(...args).first();

async function runtimeFor(url, secret, path, migrate = true) {
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{
    name: 'g1b2', modules: [
      { type: 'ESModule', path: new URL('./harness.mjs', import.meta.url).pathname },
      { type: 'ESModule', path: new URL('./dispatcher.mjs', import.meta.url).pathname },
    ],
    compatibilityDate: '2026-11-26', d1Databases: ['DB'],
    bindings: { GATEWAY_URL: url, GATEWAY_SECRET: secret },
  }], ...(path ? { resourcePersistencePath: path } : {}) }));
  const db = await runtime.getD1Database('DB', 'g1b2');
  if (migrate) {
    for (const url of [new URL('../../migrations/0001_focus.sql', import.meta.url),
                       new URL('../g1b-outbox/0001_outbox.sql', import.meta.url)]) {
      const sql = await readFile(url, 'utf8');
      await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    }
  }
  return { runtime, db };
}

async function setup(options = {}) {
  const secret = randomBytes(32).toString('hex'), clock = { now: 100 };
  const gateway = await startGateway({ secret, clock: () => clock.now,
    maxRequests: options.maxRequests ?? 100 });
  const local = await runtimeFor(gateway.url, secret);
  return { ...local, gateway, secret, clock,
    async close() { await local.runtime.dispose(); await gateway.close(); } };
}

async function run(runtime, options = {}) {
  const response = await runtime.dispatchFetch('http://local.test/dispatch', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ now: 100, timeoutMs: 50, ...options }),
  });
  if (response.status !== 200) throw new Error(`dispatcher ${response.status}: ${await response.text()}`);
  return response.json();
}

async function withLocal(fn, options) {
  const local = await setup(options);
  try { await fn(local); } finally { await local.close(); }
}

test('bounded batch delivers two events with stable IDs and D1 acknowledgments', () => withLocal(async x => {
  await append(x.db, event(1), 'owner'); await append(x.db, event(2), 'owner');
  const result = await run(x.runtime, { maxItems: 2, maxBytes: 4096 });
  assert.equal(result.delivered, 2); assert.equal(result.httpRequests, 2);
  assert.equal(result.d1Operations, 4); assert.equal(x.gateway.state.sink.size, 2);
  assert.equal((await first(x.db, `SELECT count(*) AS n FROM outbox WHERE state='acknowledged'`)).n, 2);
}));

test('lost ack retries the same event without a second logical sink row', () => withLocal(async x => {
  await append(x.db, event(1), 'owner'); x.gateway.state.faults.push('lost_ack');
  assert.equal((await run(x.runtime)).retried, 1);
  assert.equal((await run(x.runtime, { now: 102 })).delivered, 1);
  assert.deepEqual(x.gateway.state.attempts, [event(1).event_id, event(1).event_id]);
  assert.equal(x.gateway.state.sink.size, 1);
}));

test('timeout before acceptance and unavailable gateway retain retry rows', () => withLocal(async x => {
  await append(x.db, event(1), 'owner'); x.gateway.state.faults.push('timeout');
  assert.equal((await run(x.runtime)).retried, 1);
  assert.equal(x.gateway.state.sink.size, 0);
  await x.gateway.close();
  assert.equal((await run(x.runtime, { now: 102 })).retried, 1);
  assert.equal((await first(x.db, 'SELECT state,attempts FROM outbox')).attempts, 2);
}));

test('crash after lease and crash after acceptance recover on expiry', () => withLocal(async x => {
  await append(x.db, event(1), 'owner');
  assert.equal((await run(x.runtime, { fault: 'crash_after_lease' })).claimed, 1);
  assert.equal(x.gateway.state.sink.size, 0);
  assert.equal((await run(x.runtime, { now: 110, fault: 'crash_before_mark' })).claimed, 1);
  assert.equal(x.gateway.state.sink.size, 1);
  assert.equal((await run(x.runtime, { now: 120 })).delivered, 1);
  assert.equal(x.gateway.state.sink.size, 1);
  assert.deepEqual(x.gateway.state.attempts, [event(1).event_id, event(1).event_id]);
}));

test('expired lease is fenced from stale ack and reclaimed by another dispatcher', () => withLocal(async x => {
  await append(x.db, event(1), 'owner');
  await run(x.runtime, { fault: 'crash_after_lease' });
  const old = await first(x.db, 'SELECT lease_token,digest FROM outbox');
  assert.equal((await run(x.runtime, { now: 110 })).delivered, 1);
  const stale = await first(x.db, `UPDATE outbox SET state='acknowledged'
    WHERE event_id=? AND state='leased' AND lease_token=? AND lease_until>? RETURNING event_id`,
    event(1).event_id, old.lease_token, 110);
  assert.equal(stale, null);
}));

test('later session event cannot overtake retrying predecessor', () => withLocal(async x => {
  await append(x.db, event(1, 1, 'same-session'), 'owner');
  await append(x.db, event(2, 2, 'same-session'), 'owner');
  x.gateway.state.faults.push('429');
  assert.equal((await run(x.runtime, { maxItems: 2 })).retried, 1);
  assert.equal((await run(x.runtime, { now: 101 })).claimed, 0);
  assert.equal((await run(x.runtime, { now: 102, maxItems: 2 })).delivered, 2);
  assert.deepEqual(x.gateway.state.attempts, [event(1).event_id, event(2).event_id]);
}));

test('401 and 403 are terminal; 429 is retryable backpressure', () => withLocal(async x => {
  for (const [n, code] of [[1, '401'], [2, '403'], [3, '429']]) {
    await append(x.db, event(n), 'owner'); x.gateway.state.faults.push(code);
    await run(x.runtime);
    const state = await first(x.db, 'SELECT state,error_class FROM outbox WHERE event_id=?', event(n).event_id);
    assert.equal(state.state, code === '429' ? 'retry' : 'dead');
    assert.equal(state.error_class, `http_${code}`);
  }
}));

test('three retryable failures produce inspectable dead letter', () => withLocal(async x => {
  await append(x.db, event(1), 'owner');
  for (const now of [100, 102, 106]) {
    x.gateway.state.faults.push('429'); await run(x.runtime, { now });
  }
  assert.deepEqual(await first(x.db, 'SELECT state,attempts,error_class FROM outbox'),
    { state: 'dead', attempts: 3, error_class: 'http_429' });
  assert.deepEqual((await inspectDead(x.db)).map(r => r.event_id), [event(1).event_id]);
}));

test('reconciliation reports missing, orphaned, duplicate and unacknowledged IDs', () => withLocal(async x => {
  await append(x.db, event(1), 'owner');
  await append(x.db, event(2), 'owner');
  await run(x.runtime, { maxItems: 1 });
  const ids = [event(1).event_id, 'orphan'];
  const result = await reconcile(x.db, ids, [event(1).event_id, event(1).event_id]);
  assert.deepEqual(result.missing, [event(2).event_id]);
  assert.deepEqual(result.orphaned, ['orphan']);
  assert.deepEqual(result.duplicateAttempts, [event(1).event_id]);
  assert.deepEqual(result.unacknowledged, [event(2).event_id]);
  assert.equal(result.truncated, false);
}));

test('cancelled dispatch does not claim a record', () => withLocal(async x => {
  await append(x.db, event(1), 'owner');
  const controller = new AbortController(); controller.abort();
  const result = await dispatchBatch({ DB: x.db, GATEWAY_URL: x.gateway.url,
    GATEWAY_SECRET: x.secret }, { now: 100, signal: controller.signal });
  assert.equal(result.claimed, 0);
  assert.equal((await first(x.db, 'SELECT state FROM outbox')).state, 'pending');
}));

test('concurrent workerd dispatchers compete for one D1 lease', () => withLocal(async x => {
  await append(x.db, event(1), 'owner');
  const results = await Promise.all([run(x.runtime), run(x.runtime)]);
  assert.equal(results.reduce((sum, r) => sum + r.claimed, 0), 1);
  assert.equal(x.gateway.state.sink.size, 1);
}));

test('batch item and byte limits bound reads and avoid silent loss', () => withLocal(async x => {
  await append(x.db, event(1), 'owner'); await append(x.db, event(2), 'owner');
  const one = await run(x.runtime, { maxItems: 1, maxBytes: 4096 });
  assert.equal(one.delivered, 1); assert.equal(one.bytes > 0, true);
  const next = await run(x.runtime, { maxItems: 2, maxBytes: one.bytes });
  assert.equal(next.delivered, 1);
  assert.equal((await first(x.db, `SELECT count(*) AS n FROM outbox WHERE state='acknowledged'`)).n, 2);
}));

test('malformed, unsigned, bad-signature and replayed nonce requests are rejected', () => withLocal(async x => {
  const body = JSON.stringify({ event_id: event(1).event_id, session_id: event(1).session_id,
    sequence: 1, payload: JSON.stringify(event(1)),
    digest: createHash('sha256').update(JSON.stringify(event(1))).digest('hex') });
  const nonce = randomUUID(), stamp = '100';
  const headers = { 'Content-Type': 'application/json', 'X-G1B2-Key': 'synthetic',
    'X-G1B2-Time': stamp, 'X-G1B2-Nonce': nonce,
    'X-G1B2-Signature': createHmac('sha256', x.secret).update(`${stamp}\n${nonce}\n${body}`).digest('hex') };
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body })).status, 403);
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body, headers: { ...headers,
    'X-G1B2-Signature': '0'.repeat(64) } })).status, 401);
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body: '{}', headers })).status, 401);
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body, headers })).status, 200);
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body, headers })).status, 409);
  const changedPayload = JSON.stringify({ ...event(1), session_kind: 'programming' });
  const changed = JSON.stringify({ ...JSON.parse(body), payload: changedPayload,
    digest: createHash('sha256').update(changedPayload).digest('hex') });
  const changedHeaders = { ...headers, 'X-G1B2-Nonce': randomUUID() };
  changedHeaders['X-G1B2-Signature'] = createHmac('sha256', x.secret)
    .update(`100\n${changedHeaders['X-G1B2-Nonce']}\n${changed}`).digest('hex');
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body: changed,
    headers: changedHeaders })).status, 409);
  const stale = { ...headers, 'X-G1B2-Time': '0', 'X-G1B2-Nonce': randomUUID() };
  stale['X-G1B2-Signature'] = createHmac('sha256', x.secret)
    .update(`0\n${stale['X-G1B2-Nonce']}\n${body}`).digest('hex');
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body, headers: stale })).status, 401);
  const malformed = JSON.stringify({ ...JSON.parse(body), sequence: 2 });
  const malformedHeaders = { ...headers, 'X-G1B2-Nonce': randomUUID() };
  malformedHeaders['X-G1B2-Signature'] = createHmac('sha256', x.secret)
    .update(`100\n${malformedHeaders['X-G1B2-Nonce']}\n${malformed}`).digest('hex');
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body: malformed,
    headers: malformedHeaders })).status, 422);
  assert.equal((await fetch(x.gateway.url, { method: 'POST', body: 'X'.repeat(9000),
    headers: { 'Content-Type': 'application/json' } })).status, 413);
  assert.equal(x.gateway.state.sink.size, 1);
}));

test('gateway request cap rejects excess traffic with 429', () => withLocal(async x => {
  await append(x.db, event(1), 'owner'); await append(x.db, event(2), 'owner');
  assert.equal((await run(x.runtime)).delivered, 1);
  assert.equal((await run(x.runtime)).retried, 1);
  assert.equal((await first(x.db, 'SELECT error_class FROM outbox WHERE event_id=?', event(2).event_id)).error_class, 'http_429');
}, { maxRequests: 1 }));

test('restart and reconciliation converge with retained D1 and gateway sink', async () => {
  const path = await mkdtemp(join(tmpdir(), 'g1b2-'));
  const secret = randomBytes(32).toString('hex'), gateway = await startGateway({ secret, clock: () => 102 });
  try {
    let local = await runtimeFor(gateway.url, secret, path);
    try {
      await append(local.db, event(1), 'owner'); gateway.state.faults.push('lost_ack');
      await run(local.runtime, { now: 102 });
    } finally { await local.runtime.dispose(); }
    local = await runtimeFor(gateway.url, secret, path, false);
    try {
      await run(local.runtime, { now: 104 });
      assert.equal(gateway.state.sink.size, 1);
      assert.equal(gateway.state.attempts.length, 2);
      assert.equal((await first(local.db, 'SELECT state FROM outbox')).state, 'acknowledged');
    } finally { await local.runtime.dispose(); }
  } finally { await gateway.close(); await rm(path, { recursive: true, force: true }); }
});

test('30 single-event workerd dispatches retain bounded wall and resource observations', () => withLocal(async x => {
  const samples = [], before = process.memoryUsage().rss;
  for (let n = 1; n <= 30; n++) {
    await append(x.db, event(n), 'owner');
    const started = performance.now(), result = await run(x.runtime);
    samples.push({ workerWallMs: result.wallMs, hostWallMs: performance.now() - started,
      bytes: result.bytes, d1: result.d1Operations, http: result.httpRequests });
    assert.equal(result.delivered, 1);
  }
  const sorted = samples.map(x => x.workerWallMs).sort((a, b) => a - b);
  const percentile = p => sorted[Math.ceil(p * sorted.length) - 1];
  const summary = { count: samples.length, batchSize: 1,
    payloadBytesMin: Math.min(...samples.map(x => x.bytes)),
    payloadBytesMax: Math.max(...samples.map(x => x.bytes)),
    workerWallMedianMs: percentile(.5), workerWallP95Ms: percentile(.95),
    workerWallMaxMs: sorted.at(-1), hostWallMaxMs: Math.max(...samples.map(x => x.hostWallMs)),
    d1OperationsPerDelivery: 2, httpRequestsPerDelivery: 1,
    hostRssDeltaBytes: process.memoryUsage().rss - before };
  console.log('G1B2_PERF ' + JSON.stringify(summary));
}));


test('Worker dispatches mixed lifecycle and repeated zero-sequence types in persisted order', () => withLocal(async x => {
  const session = 'synthetic-mixed';
  const events = [event(1, 1, session), observation(10, 'behavioral.window', session),
    observation(11, 'behavioral.window', session), event(2, 2, session),
    observation(12, 'effort.reported', session), observation(13, 'effort.reported', session)];
  for (const e of events) await append(x.db, e, 'owner');
  assert.equal((await run(x.runtime)).delivered, 1);
  x.gateway.state.faults.push('lost_ack');
  assert.equal((await run(x.runtime)).retried, 1);
  assert.equal((await run(x.runtime, { now: 101 })).claimed, 0);
  assert.equal((await run(x.runtime, { now: 102 })).delivered, 1);
  for (let i = 2; i < events.length; i++) assert.equal((await run(x.runtime, { now: 103 + i })).delivered, 1);
  assert.deepEqual([...x.gateway.state.sink.keys()], events.map(e => e.event_id));
  assert.deepEqual(x.gateway.state.attempts, [events[0].event_id, events[1].event_id,
    ...events.slice(1).map(e => e.event_id)]);
  assert.equal((await first(x.db, "SELECT count(*) AS n FROM outbox WHERE state='acknowledged'")).n, 6);
}));
