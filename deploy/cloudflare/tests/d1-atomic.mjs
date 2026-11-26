import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';

test('workerd D1 batches roll back failed guards and resolve concurrent CAS writers', async () => {
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{name: 'atomic-test', modules: true,
    script: 'export default {fetch() {return new Response("test")}}',
    compatibilityDate: '2026-11-26', d1Databases: ['DB'] }] }));
  try {
    const db = await runtime.getD1Database('DB', 'atomic-test');
    const sql = await readFile(new URL('../migrations/0001_focus.sql', import.meta.url), 'utf8');
    await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    await db.prepare("INSERT INTO sessions VALUES ('synthetic','owner','study','behavioral',NULL,'session.started',1,'2026-11-26T00:00:00+00:00','2026-11-26T00:00:00+00:00',0)").run();
    const guarded = (version, marker) => db.batch([
      db.prepare('UPDATE sessions SET version=version+1 WHERE session_id=? AND version=?').bind('synthetic', version),
      db.prepare('INSERT INTO cas_guard VALUES (changes())'),
      db.prepare('DELETE FROM cas_guard'),
      db.prepare('INSERT INTO browser_sessions VALUES (?,?,1)').bind(marker, 'owner'),
    ]);
    const writers = await Promise.allSettled([guarded(0, 'writer-a'), guarded(0, 'writer-b')]);
    assert.equal(writers.filter(r => r.status === 'fulfilled').length, 1);
    assert.equal((await db.prepare('SELECT version FROM sessions').first()).version, 1);
    assert.equal((await db.prepare('SELECT count(*) AS n FROM browser_sessions').first()).n, 1);
    await assert.rejects(db.batch([
      db.prepare("UPDATE sessions SET version=99 WHERE session_id='synthetic'"),
      db.prepare('INSERT INTO cas_guard VALUES (0)'),
    ]));
    assert.equal((await db.prepare('SELECT version FROM sessions').first()).version, 1);
  } finally {
    await runtime.dispose();
  }
});
