import assert from 'node:assert/strict';
import { observation } from './fixtures.mjs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { append, claim, acknowledge, reject, dispatch, reconcile, MockGateway } from './outbox.mjs';

const fixture = (number, sequence = 1) => ({
  schema_version: '1.0', event_id: `00000000-0000-4000-8000-${String(number).padStart(12, '0')}`,
  idempotency_key: `synthetic-${number}`, session_id: 'synthetic-session',
  subject_id: null, source: 'synthetic', producer_version: 'g1b',
  event_type: sequence === 1 ? 'session.started' : 'session.paused', sequence,
  session_kind: 'study', privacy_mode: 'behavioral',
  event_time: `2026-11-26T00:00:0${sequence}+00:00`,
  ingested_at: `2026-11-26T00:00:0${sequence}+00:00`,
});
const first = async (db, sql, ...args) => db.prepare(sql).bind(...args).first();

async function setup(persistencePath, migrate = true) {
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{
    name: 'g1b', modules: true, script: 'export default {fetch() {return new Response("ok")}}',
    compatibilityDate: '2026-11-26', d1Databases: ['DB'],
  }], ...(persistencePath ? { resourcePersistencePath: persistencePath } : {}) }));
  const db = await runtime.getD1Database('DB', 'g1b');
  if (migrate) {
    for (const url of [new URL('../../migrations/0001_focus.sql', import.meta.url),
                       new URL('./0001_outbox.sql', import.meta.url)]) {
      const sql = await readFile(url, 'utf8');
      await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    }
  }
  return { db, runtime };
}
async function withDb(fn) {
  const { db, runtime } = await setup();
  try { await fn(db); } finally { await runtime.dispose(); }
}

test('atomic commit and rollback of event plus outbox', () => withDb(async db => {
  const event = fixture(1);
  await assert.rejects(append(db, fixture(2, 2), 'owner'));
  assert.equal((await first(db, 'SELECT count(*) AS n FROM events')).n, 0);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM outbox')).n, 0);
  assert.equal(await append(db, event, 'owner'), true);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM events')).n, 1);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM outbox')).n, 1);
  await assert.rejects(db.batch([
    db.prepare(`INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)`).bind(
      fixture(9).event_id, 'synthetic-9', event.session_id, 'session.paused',
      event.event_time, 2, JSON.stringify(fixture(9)), null, null, null),
    db.prepare(`INSERT INTO outbox (event_id,session_id,sequence,owner_id,payload,digest,state)
      VALUES (?,?,?,?,?,?,'pending')`).bind(fixture(9).event_id, event.session_id, 2,
      'owner', '{}', 'bad'),
    db.prepare('INSERT INTO cas_guard VALUES (0)'),
  ]));
  assert.equal((await first(db, 'SELECT count(*) AS n FROM events')).n, 1);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM outbox')).n, 1);
}));

test('idempotent replay and owner/payload/key conflicts', () => withDb(async db => {
  const event = fixture(1);
  assert.equal(await append(db, event, 'owner'), true);
  assert.equal(await append(db, event, 'owner'), false);
  assert.equal(await append(db, { ...event,
    ingested_at: '2026-11-26T01:00:00+00:00' }, 'owner'), false);
  await assert.rejects(append(db, event, 'other'), /identity conflict/);
  await assert.rejects(append(db, { ...event, session_kind: 'programming' }, 'owner'), /identity conflict/);
  await assert.rejects(append(db, { ...event, event_id: fixture(2).event_id }, 'owner'), /identity conflict/);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM outbox')).n, 1);
}));

test('a committed event without its matching outbox cannot be treated as replay', () => withDb(async db => {
  const event = fixture(1);
  await append(db, event, 'owner');
  await db.prepare('DELETE FROM outbox WHERE event_id=?').bind(event.event_id).run();
  await assert.rejects(append(db, event, 'owner'), /lacks matching outbox/);
}));

test('concurrent dispatchers cannot hold the same live lease', () => withDb(async db => {
  await append(db, fixture(1), 'owner');
  const claimed = await Promise.all([claim(db, 100, 'a'), claim(db, 100, 'b')]);
  assert.equal(claimed.filter(Boolean).length, 1);
  assert.equal(claimed.find(Boolean).attempts, 1);
  assert.equal(await acknowledge(db, fixture(1).event_id, 'wrong',
    { event_id: fixture(1).event_id, digest: claimed.find(Boolean).digest }, 101), false);
}));

test('expired lease recovers and rejects stale acknowledgement', () => withDb(async db => {
  const event = fixture(1); await append(db, event, 'owner');
  const old = await claim(db, 100, 'old');
  assert.equal(await claim(db, 109, 'early'), null);
  assert.equal(await acknowledge(db, event.event_id, 'old',
    { event_id: event.event_id, digest: old.digest }, 110), false);
  const fresh = await claim(db, 110, 'fresh');
  assert.equal(fresh.attempts, 2);
  assert.equal(await acknowledge(db, event.event_id, 'old',
    { event_id: event.event_id, digest: old.digest }, 111), false);
  assert.equal(await acknowledge(db, event.event_id, 'fresh',
    { event_id: event.event_id, digest: fresh.digest }, 111), true);
}));

test('retries preserve identity, bounded backoff and terminal dead letter', () => withDb(async db => {
  const event = fixture(1), sink = new MockGateway();
  await append(db, event, 'owner');
  await dispatch(db, sink, 100, 'a', 'unavailable');
  assert.deepEqual(await first(db, 'SELECT state,attempts,next_attempt_at FROM outbox'),
    { state: 'retry', attempts: 1, next_attempt_at: 102 });
  assert.equal(await claim(db, 101, 'too-early'), null);
  await dispatch(db, sink, 102, 'b', 'timeout');
  await dispatch(db, sink, 106, 'c', 'unavailable');
  assert.deepEqual(await first(db, 'SELECT state,attempts,error_class FROM outbox'),
    { state: 'dead', attempts: 3, error_class: 'unavailable' });
  assert.equal(await claim(db, 1000, 'no-revive'), null);
  assert.deepEqual((await reconcile(db, sink)).missing, [event.event_id]);
}));

test('lost acknowledgement and crash before mark cause duplicate attempts but one sink record', () => withDb(async db => {
  const event = fixture(1), sink = new MockGateway(); await append(db, event, 'owner');
  await dispatch(db, sink, 100, 'a', 'lost_ack');
  await dispatch(db, sink, 102, 'b', 'crash_before_mark');
  await dispatch(db, sink, 112, 'c');
  assert.equal(sink.records.size, 1);
  assert.deepEqual((await reconcile(db, sink)).duplicateAttempts, [event.event_id]);
  assert.equal((await first(db, 'SELECT state FROM outbox')).state, 'acknowledged');
}));

test('crash after lease is recovered after expiration', () => withDb(async db => {
  const sink = new MockGateway(); await append(db, fixture(1), 'owner');
  await dispatch(db, sink, 100, 'old', 'crash_after_lease');
  assert.equal(sink.records.size, 0);
  await dispatch(db, sink, 110, 'new');
  assert.equal(sink.records.size, 1);
  assert.deepEqual((await reconcile(db, sink)).unacknowledged, []);
}));

test('session sequence blocks out-of-order retry across events', () => withDb(async db => {
  const sink = new MockGateway();
  await append(db, fixture(1), 'owner'); await append(db, fixture(2, 2), 'owner');
  await dispatch(db, sink, 100, 'a', 'unavailable');
  assert.equal(await claim(db, 101, 'b'), null);
  await dispatch(db, sink, 102, 'c');
  await dispatch(db, sink, 103, 'd');
  assert.deepEqual([...sink.records.keys()], [fixture(1).event_id, fixture(2).event_id]);
  assert.deepEqual((await reconcile(db, sink)).missing, []);
}));

test('reconciliation exposes missing, orphaned and duplicate attempts', () => withDb(async db => {
  const sink = new MockGateway(); await append(db, fixture(1), 'owner');
  sink.deliver({ event_id: 'orphan', digest: 'a', session_id: 'x' });
  const before = await reconcile(db, sink);
  assert.deepEqual(before.missing, [fixture(1).event_id]);
  assert.deepEqual(before.orphaned, ['orphan']);
  await dispatch(db, sink, 100, 'a');
  sink.deliver({ event_id: fixture(1).event_id,
    digest: (await first(db, 'SELECT digest FROM outbox')).digest, session_id: 'synthetic-session' });
  assert.deepEqual((await reconcile(db, sink)).duplicateAttempts, [fixture(1).event_id]);
}));

test('Miniflare D1 persists over runtime restart and converges after gateway recovery', async () => {
  const path = await mkdtemp(join(tmpdir(), 'cogniflow-g1b-'));
  const sink = new MockGateway();
  try {
    const before = await setup(path);
    try {
      await append(before.db, fixture(1), 'owner');
      await dispatch(before.db, sink, 100, 'before-restart', 'unavailable');
    } finally { await before.runtime.dispose(); }
    const after = await setup(path, false);
    try {
      assert.equal((await first(after.db, 'SELECT state FROM outbox')).state, 'retry');
      await dispatch(after.db, sink, 102, 'after-restart');
      assert.deepEqual((await reconcile(after.db, sink)).unacknowledged, []);
      assert.equal(sink.records.size, 1);
    } finally { await after.runtime.dispose(); }
  } finally { await rm(path, { recursive: true, force: true }); }
});

test('invalid ack and explicit terminal failure stay inspectable', () => withDb(async db => {
  const event = fixture(1); await append(db, event, 'owner');
  const lease = await claim(db, 100, 'a');
  assert.equal(await acknowledge(db, event.event_id, 'a',
    { event_id: event.event_id, digest: '0'.repeat(64) }, 100), false);
  assert.equal(await reject(db, event.event_id, 'a', 'schema_rejected', 100, true), true);
  assert.deepEqual(await first(db, 'SELECT state,error_class,digest FROM outbox'),
    { state: 'dead', error_class: 'schema_rejected', digest: lease.digest });
}));

for (const types of [['behavioral.window', 'behavioral.window'],
                     ['effort.reported', 'effort.reported'],
                     ['behavioral.window', 'effort.reported']]) {
  test(`distinct zero-sequence ${types.join(' + ')} persist and replay`, () => withDb(async db => {
    await append(db, fixture(1), 'owner');
    const before = await first(db, 'SELECT state,last_sequence,last_event_time FROM sessions');
    for (const [i, type] of types.entries()) {
      const event = observation(i + 10, type);
      assert.equal(await append(db, event, 'owner'), true);
      const original = await first(db, 'SELECT * FROM outbox WHERE event_id=?', event.event_id);
      assert.equal(original.sequence, 0);
      assert.equal(JSON.parse(original.payload).sequence, undefined);
      assert.equal(await append(db, { ...event, ingested_at: '2026-11-26T01:00:00+00:00' }, 'owner'), false);
      assert.deepEqual(await first(db, 'SELECT * FROM outbox WHERE event_id=?', event.event_id), original);
      await assert.rejects(append(db, { ...event, event_id: fixture(99).event_id }, 'owner'), /identity conflict/);
      await assert.rejects(append(db, { ...event, idempotency_key: 'changed' }, 'owner'), /identity conflict/);
      await assert.rejects(append(db, { ...event, source: 'changed' }, 'owner'), /identity conflict/);
    }
    assert.equal((await first(db, 'SELECT count(*) AS n FROM events WHERE sequence=0')).n, 2);
    assert.equal((await first(db, 'SELECT count(*) AS n FROM outbox WHERE sequence=0')).n, 2);
    assert.deepEqual(await first(db, 'SELECT state,last_sequence,last_event_time FROM sessions'), before);
    await append(db, fixture(2, 2), 'owner');
    await append(db, { ...fixture(3, 3), event_type: 'session.resumed' }, 'owner');
    await assert.rejects(append(db, fixture(4, 3), 'owner'));
    await assert.rejects(append(db, fixture(5, 5), 'owner'));
    // Isolate the outbox constraint from events' existing positive-sequence index.
    await db.prepare(`INSERT INTO events VALUES ('constraint-probe','probe','synthetic-session',
      'effort.reported','t',0,'{}',NULL,NULL,NULL)`).run();
    await assert.rejects(db.prepare(`INSERT INTO outbox
      (event_id,session_id,sequence,owner_id,payload,digest,state)
      VALUES ('constraint-probe','synthetic-session',2,'owner','{}','digest','pending')`)
      .run(), /outbox.session_id, outbox.sequence/i);
    const index = await first(db, "SELECT sql FROM sqlite_master WHERE name='outbox_lifecycle_sequence'");
    assert.match(index.sql, /WHERE sequence > 0/);
  }));
}

test('zero-sequence insert failure rolls back event and session version', () => withDb(async db => {
  await append(db, fixture(1), 'owner');
  await db.prepare("CREATE TRIGGER fail_delivery BEFORE INSERT ON outbox WHEN NEW.sequence=0 BEGIN SELECT RAISE(ABORT,'injected outbox failure'); END").run();
  const before = await first(db, 'SELECT * FROM sessions');
  await assert.rejects(append(db, observation(10), 'owner'), /injected outbox failure/);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM events')).n, 1);
  assert.equal((await first(db, 'SELECT count(*) AS n FROM outbox')).n, 1);
  assert.deepEqual(await first(db, 'SELECT * FROM sessions'), before);
  await db.prepare('DROP TRIGGER fail_delivery').run();
  await assert.rejects(append(db, observation(10), 'wrong-owner'));
  assert.equal((await first(db, 'SELECT count(*) AS n FROM events')).n, 1);
}));

test('mixed insertion order fences concurrent leases, dead letters and recovery', () => withDb(async db => {
  const events = [fixture(1), observation(10), fixture(2, 2), observation(11, 'effort.reported')];
  for (const event of events) await append(db, event, 'owner');
  const sink = new MockGateway();
  await dispatch(db, sink, 100, 'start');
  const leases = await Promise.all([claim(db, 101, 'a'), claim(db, 101, 'b')]);
  assert.equal(leases.filter(Boolean).length, 1);
  const lease = leases.find(Boolean);
  assert.equal(lease.event_id, events[1].event_id);
  assert.equal(await claim(db, 102, 'blocked'), null);
  assert.equal(await reject(db, lease.event_id, lease.lease_token, 'schema_rejected', 102, true), true);
  assert.equal(await claim(db, 200, 'dead-blocks'), null);
  assert.deepEqual((await reconcile(db, sink)).unacknowledged, events.slice(1).map(e => e.event_id));
  // Explicit test-only operator repair after cause resolution; no automatic dead-letter revival.
  await db.prepare("UPDATE outbox SET state='retry',attempts=0,next_attempt_at=200 WHERE event_id=? AND state='dead'")
    .bind(lease.event_id).run();
  await dispatch(db, sink, 200, 'recovered', 'timeout');
  assert.equal(await claim(db, 201, 'blocked-again'), null);
  await dispatch(db, sink, 202, 'crashed', 'crash_before_mark');
  await dispatch(db, sink, 212, 'restarted');
  await dispatch(db, sink, 213, 'pause');
  await dispatch(db, sink, 214, 'effort');
  assert.deepEqual([...sink.records.keys()], events.map(e => e.event_id));
  assert.deepEqual((await reconcile(db, sink)).unacknowledged, []);
  assert.deepEqual((await reconcile(db, sink)).duplicateAttempts, [lease.event_id]);
}));


test('zero-sequence retry survives persistent workerd restart with stable order and identity', async () => {
  const path = await mkdtemp(join(tmpdir(), 'cogniflow-g1b3-'));
  const sink = new MockGateway();
  const events = [fixture(1), observation(10), fixture(2, 2), observation(11, 'effort.reported')];
  let original;
  try {
    const before = await setup(path);
    try {
      for (const event of events) await append(before.db, event, 'owner');
      await dispatch(before.db, sink, 100, 'start');
      await dispatch(before.db, sink, 101, 'lost', 'lost_ack');
      original = await first(before.db, 'SELECT * FROM outbox WHERE event_id=?', events[1].event_id);
    } finally { await before.runtime.dispose(); }
    const after = await setup(path, false);
    try {
      assert.deepEqual(await first(after.db, 'SELECT * FROM outbox WHERE event_id=?', events[1].event_id), original);
      await dispatch(after.db, sink, 103, 'recover');
      await dispatch(after.db, sink, 104, 'pause');
      await dispatch(after.db, sink, 105, 'effort');
      assert.deepEqual([...sink.records.keys()], events.map(e => e.event_id));
      assert.deepEqual((await reconcile(after.db, sink)).unacknowledged, []);
    } finally { await after.runtime.dispose(); }
  } finally { await rm(path, { recursive: true, force: true }); }
});
