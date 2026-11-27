import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { append } from '../g1b-outbox/outbox.mjs';

const event = n => ({ schema_version: '1.0',
  event_id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  idempotency_key: `g1b3-${n}`, session_id: `synthetic-g1b3-${n}`,
  subject_id: null, source: 'synthetic', producer_version: 'g1b3',
  event_type: 'session.started', sequence: 1, session_kind: 'study',
  privacy_mode: 'behavioral', event_time: '2026-11-26T00:00:01+00:00',
  ingested_at: '2026-11-26T00:00:01+00:00' });

test('isolated service-bound Worker dispatches and rejects anonymous access', async () => {
  const secret = 'synthetic-local-only-'.repeat(4), token = 'synthetic-test-token'.repeat(4);
  const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [
    { name: 'dispatcher', modules: [
      { type: 'ESModule', path: new URL('./dispatcher-worker.mjs', import.meta.url).pathname },
      { type: 'ESModule', path: new URL('../g1b2-gateway/dispatcher.mjs', import.meta.url).pathname },
    ], compatibilityDate: '2026-11-27', d1Databases: { DB: 'g1b3-db' },
    bindings: { GATEWAY_SECRET: secret, RUN_TOKEN: token,
      GATEWAY_URL: 'http://gateway.internal/ingest' },
    serviceBindings: { GATEWAY: 'gateway' } },
    { name: 'gateway', modules: true,
      scriptPath: new URL('./gateway.mjs', import.meta.url).pathname,
      compatibilityDate: '2026-11-27', d1Databases: { DB: 'g1b3-db' },
      bindings: { GATEWAY_SECRET: secret } },
  ] }));
  try {
    const db = await runtime.getD1Database('DB', 'dispatcher');
    for (const url of [new URL('../../migrations/0001_focus.sql', import.meta.url),
      new URL('../g1b-outbox/0001_outbox.sql', import.meta.url),
      new URL('./0002_gateway.sql', import.meta.url)]) {
      const sql = (await readFile(url, 'utf8')).replace(/^--.*$/gm, '');
      await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
    }
    await append(db, event(1), 'synthetic-owner');
    const unauthorized = await runtime.dispatchFetch('http://dispatcher/dispatch', {
      method: 'POST', body: '{}', headers: { 'Content-Type': 'application/json' } });
    assert.equal(unauthorized.status, 401);
    const response = await runtime.dispatchFetch('http://dispatcher/dispatch', {
      method: 'POST', body: '{}', headers: { 'Content-Type': 'application/json',
        'X-G1B3-Run-Token': token } });
    assert.equal(response.status, 200, await response.clone().text());
    const result = await response.json();
    assert.equal(result.delivered, 1);
    assert.equal((await db.prepare("SELECT count(*) AS n FROM outbox WHERE state='acknowledged'").first()).n, 1);
    assert.equal((await db.prepare('SELECT count(*) AS n FROM gateway_receipts').first()).n, 1);
  } finally { await runtime.dispose(); }
});
