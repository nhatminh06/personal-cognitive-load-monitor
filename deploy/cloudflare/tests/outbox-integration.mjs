import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { test } from 'node:test';
import { transform } from 'esbuild';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';

const source = await readFile(new URL('../src/worker.ts', import.meta.url), 'utf8');
const compiled = await transform(`${source}\nexport {mutate};`, { loader: 'ts', format: 'esm' });
const { mutate } = await import(`data:text/javascript;base64,${Buffer.from(compiled.code).toString('base64')}`);
const stamp = '2026-11-26T00:00:00+00:00';
const event = (session_id, sequence = 1, event_type = 'session.started') => ({
  schema_version: '1.0', event_id: randomUUID(), idempotency_key: randomUUID(), session_id,
  subject_id: null, event_time: stamp, ingested_at: stamp, source: 'synthetic', producer_version: 'g1d1',
  event_type, sequence, session_kind: 'study', privacy_mode: 'behavioral', planned_duration_seconds: null,
});
const count = async (db, table, session) => (await db.prepare(`SELECT count(*) AS n FROM ${table} WHERE session_id=?`).bind(session).first()).n;

test('forward migration preserves old data and enabled mutations atomically enqueue once', async () => {
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{ name: 'g1d1', modules: true,
    script: 'export default {fetch() {return new Response("test")}}', compatibilityDate: '2026-11-26', d1Databases: ['DB'] }] }));
  try {
    const db = await runtime.getD1Database('DB', 'g1d1');
    const base = await readFile(new URL('../migrations/0001_focus.sql', import.meta.url), 'utf8');
    await db.batch(base.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    const old = event(`old-${randomUUID()}`);
    await mutate(db, 'create', old, 'owner');
    const migration = await readFile(new URL('../migrations/0002_outbox.sql', import.meta.url), 'utf8');
    await db.batch(migration.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    assert.equal(await count(db, 'events', old.session_id), 1);
    assert.equal(await count(db, 'outbox', old.session_id), 0);
    await assert.rejects(db.batch(migration.split(';').filter(s => s.trim()).map(s => db.prepare(s))));
    const sid = `new-${randomUUID()}`, started = event(sid);
    const results = await Promise.all([mutate(db, 'create', { ...started }, 'owner', true),
      mutate(db, 'create', { ...started }, 'owner', true), mutate(db, 'create', { ...started }, 'owner', true)]);
    assert.deepEqual(results.map(x => x[1]).sort(), [false, false, true]);
    assert.equal(await count(db, 'events', sid), 1);
    assert.equal(await count(db, 'outbox', sid), 1);
    assert.equal((await db.prepare('SELECT payload,digest FROM outbox WHERE event_id=?').bind(started.event_id).first()).payload,
      (await db.prepare('SELECT event_json FROM events WHERE event_id=?').bind(started.event_id).first()).event_json);
    await assert.rejects(mutate(db, 'create', { ...started, event_id: randomUUID() }, 'owner', true));
    await assert.rejects(mutate(db, 'create', { ...started }, 'other', true));
    const next = event(sid, 2, 'session.paused');
    await mutate(db, 'transitions', next, 'owner', true);
    assert.equal(await count(db, 'outbox', sid), 2);
    const window_id = randomUUID(), window_start = stamp, window_end = '2026-11-26T00:05:00+00:00';
    await db.prepare('INSERT INTO windows VALUES (?,?,?,?)').bind(window_id, sid, window_start, window_end).run();
    const activity = { ...event(sid, 0, 'behavioral.window'), window_id, window_start, window_end,
      event_time: window_end, feature_cutoff: window_end };
    const label = { ...event(sid, 0, 'effort.reported'), window_id, window_start, window_end,
      event_time: window_end, feature_cutoff: window_end, reported_at: window_end, label_id: randomUUID() };
    await mutate(db, 'activity', activity, 'owner', true);
    await mutate(db, 'labels', label, 'owner', true);
    assert.equal(await count(db, 'outbox', sid), 4);
    assert.equal((await db.prepare('SELECT count(*) AS n FROM outbox WHERE session_id=? AND sequence=0').bind(sid).first()).n, 2);
    await assert.rejects(mutate(db, 'transitions', event(sid, 2, 'session.completed'), 'owner', true));
    assert.equal(await count(db, 'events', sid), 4);
    const broken = `broken-${randomUUID()}`;
    await db.prepare('CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(FAIL, "synthetic outbox failure"); END').run();
    await assert.rejects(mutate(db, 'create', event(broken), 'owner', true), /synthetic outbox failure/);
    assert.equal(await count(db, 'sessions', broken), 0);
    assert.equal(await count(db, 'events', broken), 0);
    await db.prepare('DROP TRIGGER fail_outbox').run();
    const disabled = event(`disabled-${randomUUID()}`);
    await mutate(db, 'create', disabled, 'owner');
    assert.equal(await count(db, 'outbox', disabled.session_id), 0);
  } finally { await runtime.dispose(); }
});
