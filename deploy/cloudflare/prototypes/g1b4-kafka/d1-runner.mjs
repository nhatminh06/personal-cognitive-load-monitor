// Test-only Miniflare D1 driver. JSON commands arrive on stdin; synthetic secret is an env var.
import { readFile } from 'node:fs/promises';
import { stdin } from 'node:process';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { append, acknowledge } from '../g1b-outbox/outbox.mjs';

const input = await new Promise((resolve, reject) => {
  let raw = ''; stdin.setEncoding('utf8'); stdin.on('data', x => raw += x);
  stdin.on('end', () => { try { resolve(JSON.parse(raw)); } catch (error) { reject(error); } });
});
const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{
  name: 'g1b4', modules: [
    { type: 'ESModule', path: new URL('../g1b2-gateway/harness.mjs', import.meta.url).pathname },
    { type: 'ESModule', path: new URL('../g1b2-gateway/dispatcher.mjs', import.meta.url).pathname },
  ], compatibilityDate: '2026-11-27', d1Databases: ['DB'],
  bindings: { GATEWAY_URL: process.env.G1B4_URL, GATEWAY_SECRET: process.env.G1B4_SECRET },
}], resourcePersistencePath: process.env.G1B4_D1_PATH }));
try {
  const db = await runtime.getD1Database('DB', 'g1b4');
  const results = [];
  for (const action of input.actions) {
    if (action.type === 'init') {
      for (const url of [new URL('../../migrations/0001_focus.sql', import.meta.url),
        new URL('../g1b-outbox/0001_outbox.sql', import.meta.url)]) {
        const sql = (await readFile(url, 'utf8')).replace(/^--.*$/gm, '');
        await db.batch(sql.split(';').filter(s => s.trim()).map(s => db.prepare(s)));
      }
      results.push(true);
    } else if (action.type === 'append') {
      results.push(await append(db, action.event, 'synthetic-owner'));
    } else if (action.type === 'dispatch') {
      const response = await runtime.dispatchFetch('http://local.test/dispatch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ maxItems: 1, maxBytes: 4096, timeoutMs: 3000,
          ...action.options }),
      });
      results.push({ http: response.status, body: await response.json() });
    } else if (action.type === 'concurrent') {
      const send = () => runtime.dispatchFetch('http://local.test/dispatch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ maxItems: 1, maxBytes: 4096, timeoutMs: 3000 }),
      });
      const responses = await Promise.all([send(), send()]);
      results.push(await Promise.all(responses.map(async response => ({
        http: response.status, body: await response.json(),
      }))));
    } else if (action.type === 'state') {
      results.push((await db.prepare('SELECT event_id,state,attempts,lease_token,digest,delivery_order FROM outbox ORDER BY delivery_order').all()).results);
    } else if (action.type === 'stale_ack') {
      results.push(await acknowledge(db, action.event_id, action.token,
        { event_id: action.event_id, digest: action.digest }, action.now));
    } else {
      throw new Error('unknown test command');
    }
  }
  process.stdout.write(JSON.stringify(results) + '\n');
} finally { await runtime.dispose(); }
