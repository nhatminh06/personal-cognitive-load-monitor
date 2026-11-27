// Disposable workers.dev test entry. All private routes require a synthetic secret.
import { dispatchBatch } from '../g1b2-gateway/dispatcher.mjs';

const reply = (body, status = 200) => Response.json(body, { status,
  headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
const equal = (a, b) => {
  if (a.length !== b.length) return false;
  let diff = 0; for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
};
export default { async fetch(request, env) {
  const path = new URL(request.url).pathname;
  if (request.method === 'GET' && path === '/health') return reply({ status: 'healthy' });
  if (!env.RUN_TOKEN || !equal(request.headers.get('X-G1B3-Run-Token') || '', env.RUN_TOKEN)) {
    return reply({ error: 'unauthorized' }, 401);
  }
  try {
    if (request.method === 'GET' && path === '/status') {
      const rows = (await env.DB.prepare('SELECT state,count(*) AS n FROM outbox GROUP BY state').all()).results;
      const receipts = await env.DB.prepare('SELECT count(*) AS n FROM gateway_receipts').first();
      return reply({ states: Object.fromEntries(rows.map(x => [x.state, x.n])), receipts: receipts.n });
    }
    if (request.method !== 'POST' || path !== '/dispatch') return reply({ error: 'not found' }, 404);
    if (Number(request.headers.get('Content-Length') || 0) > 256) return reply({ error: 'invalid request' }, 422);
    const body = await request.text(); if (body.length > 256) return reply({ error: 'invalid request' }, 422);
    const options = body ? JSON.parse(body) : {};
    if (!options || typeof options !== 'object' || Array.isArray(options) ||
        Object.keys(options).some(x => x !== 'fault') ||
        ![undefined, 'crash_after_lease', 'crash_before_mark', 'retry_429', 'bad_sig'].includes(options.fault)) {
      return reply({ error: 'invalid request' }, 422);
    }
    return reply(await dispatchBatch(env, { maxItems: 1, maxBytes: 4096,
      timeoutMs: 2000, ...(options.fault ? { fault: options.fault } : {}) }));
  } catch { return reply({ error: 'unavailable' }, 503); }
} };
