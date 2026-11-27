// Local qualification driver: real D1, Worker-compatible dispatcher, verified Node TLS.
import { readFile } from 'node:fs/promises';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { append } from '../prototypes/g1b-outbox/outbox.mjs';
import { dispatchBatch } from '../prototypes/g1b2-gateway/dispatcher.mjs';

const commands = JSON.parse(await new Promise(resolve => {
  let raw = ''; process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => raw += chunk);
  process.stdin.on('end', () => resolve(raw));
}));
const runtime = new Miniflare(convertV4MiniflareOptions({ workers: [{ name: 'g1d2', modules: true,
  script: 'export default {fetch() {return new Response("local")}}',
  compatibilityDate: '2026-11-27', d1Databases: ['DB'] }],
  resourcePersistencePath: process.env.G1D2_D1_PATH }));
try {
  const db = await runtime.getD1Database('DB', 'g1d2');
  const results = [];
  for (const command of commands) {
    if (command.type === 'init') {
      for (const path of ['../migrations/0001_focus.sql', '../migrations/0002_outbox.sql']) {
        const sql = (await readFile(new URL(path, import.meta.url), 'utf8')).replace(/^--.*$/gm, '');
        await db.batch(sql.split(';').filter(x => x.trim()).map(x => db.prepare(x)));
      }
      results.push(true);
    } else if (command.type === 'append') {
      results.push(await append(db, command.event, 'synthetic-owner'));
    } else if (command.type === 'dispatch') {
      results.push(await dispatchBatch({ DB: db, GATEWAY_URL: process.env.G1D2_URL, GATEWAY_REQUIRE_HTTPS: 'true',
        GATEWAY_SECRET: process.env.G1D2_SECRET, GATEWAY_KEY_ID: process.env.G1D2_KEY_ID },
      { maxItems: 1, maxBytes: 4096, timeoutMs: 2000, ...command.options }));
    } else if (command.type === 'concurrent') {
      const env = { DB: db, GATEWAY_URL: process.env.G1D2_URL, GATEWAY_REQUIRE_HTTPS: 'true',
        GATEWAY_SECRET: process.env.G1D2_SECRET, GATEWAY_KEY_ID: process.env.G1D2_KEY_ID };
      results.push(await Promise.all([dispatchBatch(env), dispatchBatch(env)]));
    } else if (command.type === 'state') {
      results.push((await db.prepare('SELECT event_id,state,attempts FROM outbox ORDER BY delivery_order').all()).results);
    } else throw new Error('invalid command');
  }
  process.stdout.write(JSON.stringify(results) + '\n');
} finally { await runtime.dispose(); }
