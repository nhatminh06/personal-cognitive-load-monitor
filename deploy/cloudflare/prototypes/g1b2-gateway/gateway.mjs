// Loopback-only synthetic HTTP gateway; never publish this server.
import { createHash, createHmac, timingSafeEqual } from 'node:crypto';
import { createServer } from 'node:http';

const idPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const digestPattern = /^[0-9a-f]{64}$/;
const sessionPattern = /^[A-Za-z0-9._:-]{1,128}$/;
const fail = (res, code) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end('{}'); };

export async function startGateway({ secret, clock, maxRequests = 100, maxBody = 8192 }) {
  if (!secret || typeof clock !== 'function') throw new Error('invalid gateway configuration');
  const state = { sink: new Map(), attempts: [], faults: [], nonces: new Map(), requests: 0 };
  const server = createServer(async (req, res) => {
    if (req.method !== 'POST' || req.url !== '/ingest') return fail(res, 404);
    const now = clock();
    for (const [nonce, expires] of state.nonces) if (expires < now) state.nonces.delete(nonce);
    if (++state.requests > maxRequests) return fail(res, 429);
    if (Number(req.headers['content-length'] || 0) > maxBody) return fail(res, 413);
    let body = '';
    try {
      for await (const chunk of req) {
        body += chunk;
        if (Buffer.byteLength(body) > maxBody) return fail(res, 413);
      }
      if (req.headers['content-type'] !== 'application/json' ||
          req.headers['x-g1b2-key'] !== 'synthetic') return fail(res, 403);
      const stamp = req.headers['x-g1b2-time'], nonce = req.headers['x-g1b2-nonce'];
      const signature = req.headers['x-g1b2-signature'];
      if (typeof stamp !== 'string' || !/^\d{1,12}$/.test(stamp) ||
          Math.abs(Number(stamp) - now) > 30 || typeof nonce !== 'string' ||
          !idPattern.test(nonce) || typeof signature !== 'string' ||
          !digestPattern.test(signature)) return fail(res, 401);
      const expected = createHmac('sha256', secret).update(`${stamp}\n${nonce}\n${body}`).digest();
      if (!timingSafeEqual(expected, Buffer.from(signature, 'hex'))) return fail(res, 401);
      if (state.nonces.has(nonce)) return fail(res, 409);
      state.nonces.set(nonce, now + 30);
      const item = JSON.parse(body);
      if (!item || typeof item !== 'object' || Array.isArray(item) ||
          Object.keys(item).sort().join(',') !== 'digest,event_id,payload,sequence,session_id' ||
          !idPattern.test(item.event_id) || !sessionPattern.test(item.session_id) ||
          !Number.isSafeInteger(item.sequence) || item.sequence < 0 ||
          !digestPattern.test(item.digest) || typeof item.payload !== 'string' ||
          Buffer.byteLength(item.payload) > 4096 ||
          createHash('sha256').update(item.payload).digest('hex') !== item.digest) {
        return fail(res, 422);
      }
      const event = JSON.parse(item.payload);
      const lifecycle = ['session.started', 'session.paused', 'session.resumed',
        'session.completed', 'session.cancelled'].includes(event.event_type);
      if (lifecycle ? !Number.isSafeInteger(event.sequence) || event.sequence < 1 :
          !['behavioral.window', 'effort.reported'].includes(event.event_type) ||
          (event.sequence ?? 0) !== 0) return fail(res, 422);
      if (event.event_id !== item.event_id || event.session_id !== item.session_id ||
          (event.sequence ?? 0) !== item.sequence || event.schema_version !== '1.0') return fail(res, 422);
      const fault = state.faults.shift() || 'ok';
      if (fault === '401' || fault === '403' || fault === '429') return fail(res, Number(fault));
      if (fault === 'timeout') return setTimeout(() => { if (!res.destroyed) fail(res, 504); }, 200);
      const existing = state.sink.get(item.event_id);
      if (existing && existing.digest !== item.digest) return fail(res, 409);
      state.attempts.push(item.event_id);
      state.sink.set(item.event_id, { digest: item.digest, session_id: item.session_id });
      if (fault === 'lost_ack') return setTimeout(() => { if (!res.destroyed) fail(res, 504); }, 200);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ event_id: item.event_id, digest: item.digest }));
    } catch { if (!res.headersSent) fail(res, 400); }
  });
  await new Promise((resolve, reject) => server.listen(0, '127.0.0.1', error => error ? reject(error) : resolve()));
  return { url: `http://127.0.0.1:${server.address().port}/ingest`, state,
    async close() { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); } };
}
