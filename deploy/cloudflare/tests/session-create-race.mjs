import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { transform } from 'esbuild';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';

const source = await readFile(new URL('../src/worker.ts', import.meta.url), 'utf8');
const compiled = await transform(`${source}\nexport {mutate};`, { loader: 'ts', format: 'esm' });
const { mutate } = await import(`data:text/javascript;base64,${Buffer.from(compiled.code).toString('base64')}`);
const oldSource = source.replace("statements=[stmt(db,'INSERT INTO sessions", "if(await one(db,'SELECT 1 FROM sessions WHERE session_id=?',e.session_id))fail(409,'Session already exists');statements=[stmt(db,'INSERT INTO sessions");
const oldCompiled = await transform(`${oldSource}\nexport {mutate};`, { loader: 'ts', format: 'esm' });
const { mutate: oldMutate } = await import(`data:text/javascript;base64,${Buffer.from(oldCompiled.code).toString('base64')}`);
const stamp = '2026-11-25T00:00:00+00:00';
const event = session_id => ({ schema_version: '1.0', event_id: randomUUID(), session_id,
  subject_id: null, event_time: stamp, ingested_at: stamp, source: 'synthetic_test',
  producer_version: '1.0', idempotency_key: randomUUID(), event_type: 'session.started',
  sequence: 1, session_kind: 'study', privacy_mode: 'behavioral', planned_duration_seconds: null });

test('session create races settle to one atomic event; conflicts fail closed', async () => {
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{ name: 'race-test', modules: true,
    script: 'export default {fetch() {return new Response("test")}}', compatibilityDate: '2026-11-26', d1Databases: ['DB'] }] }));
  try {
    const db = await runtime.getD1Database('DB', 'race-test');
    const sql = await readFile(new URL('../migrations/0001_focus.sql', import.meta.url), 'utf8');
    await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    for (let group = 0; group < 30; group++) {
      const e = event(`race-${randomUUID()}`);
      const results = await Promise.all([mutate(db, 'create', { ...e }, 'owner'), mutate(db, 'create', { ...e }, 'owner'), mutate(db, 'create', { ...e }, 'owner')]);
      assert.deepEqual(results.map(r => r[1]).sort(), [false, false, true]);
      assert.equal(new Set(results.map(r => r[0].session_id)).size, 1);
      assert.equal((await db.prepare('SELECT count(*) AS n FROM sessions WHERE session_id=?').bind(e.session_id).first()).n, 1);
      assert.equal((await db.prepare('SELECT count(*) AS n FROM events WHERE session_id=?').bind(e.session_id).first()).n, 1);
      await assert.rejects(mutate(db, 'create', { ...e, session_kind: 'programming' }, 'owner'), /Event identity or idempotency key/);
      await assert.rejects(mutate(db, 'create', { ...e, event_id: randomUUID() }, 'owner'), /Event identity or idempotency key/);
      await assert.rejects(mutate(db, 'create', { ...e, event_id: randomUUID(), idempotency_key: randomUUID() }, 'owner'), /Concurrent write conflicts/);
      await assert.rejects(mutate(db, 'create', { ...e }, 'other-owner'), /Event identity or idempotency key/);
    }
    const e = event(`failure-${randomUUID()}`);
    const broken = { ...db, prepare: db.prepare.bind(db), batch: async () => { throw new Error('database unavailable'); } };
    await assert.rejects(mutate(broken, 'create', e, 'owner'), /database unavailable/);
    assert.equal((await db.prepare('SELECT count(*) AS n FROM sessions WHERE session_id=?').bind(e.session_id).first()).n, 0);
  } finally { await runtime.dispose(); }
});

test('controlled competing commit reproduces the old exact 409 body', async () => {
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{ name: 'race-repro', modules: true,
    script: 'export default {fetch() {return new Response("test")}}', compatibilityDate: '2026-11-26', d1Databases: ['DB'] }] }));
  try {
    const db = await runtime.getD1Database('DB', 'race-repro');
    const sql = await readFile(new URL('../migrations/0001_focus.sql', import.meta.url), 'utf8');
    await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    for (const [implementation, expected] of [[oldMutate, 409], [mutate, 200]]) {
      const e = event(`interleaved-${randomUUID()}`);
      let release, entered;
      const gate = new Promise(resolve => { release = resolve; });
      const seen = new Promise(resolve => { entered = resolve; });
      let intercepted = false;
      const laggingDb = { prepare(query) {
        const statement = db.prepare(query);
        if (!intercepted && query.includes('FROM events e JOIN sessions s')) {
          intercepted = true;
          return { bind(...args) { const bound = statement.bind(...args); return { all: async () => { entered(); await gate; return { results: [] }; } }; } };
        }
        return statement;
      }, batch: db.batch.bind(db) };
      const lagger = implementation(laggingDb, 'create', { ...e }, 'owner');
      await seen;
      const winner = await implementation(db, 'create', { ...e }, 'owner');
      assert.equal(winner[1], true);
      release();
      if (expected === 409) {
        const error = await lagger.catch(reason => reason);
        assert.equal(error.status, 409);
        assert.equal(JSON.stringify({ detail: error.message }), '{"detail":"Session already exists"}');
      } else {
        const replay = await lagger;
        assert.equal(replay[1], false);
        assert.equal(replay[0].event_id, winner[0].event_id);
      }
    }
  } finally { await runtime.dispose(); }
});
