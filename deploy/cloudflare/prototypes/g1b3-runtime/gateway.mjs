// Disposable internal mock gateway. Service binding only; no public route.
const encoder = new TextEncoder();
const id = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const hex = /^[0-9a-f]{64}$/;
const reply = (status, body = {}) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
const equal = (a, b) => {
  if (a.length !== b.length) return false;
  let diff = 0; for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
};
async function sha256(text) {
  const bytes = await crypto.subtle.digest('SHA-256', encoder.encode(text));
  return Array.from(new Uint8Array(bytes), x => x.toString(16).padStart(2, '0')).join('');
}
async function hmac(secret, text) {
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const bytes = await crypto.subtle.sign('HMAC', key, encoder.encode(text));
  return Array.from(new Uint8Array(bytes), x => x.toString(16).padStart(2, '0')).join('');
}
async function limitedBody(request) {
  const reader = request.body?.getReader(); let size = 0; const chunks = [];
  if (reader) for (;;) {
    const { done, value } = await reader.read(); if (done) break;
    size += value.byteLength; if (size > 8192) { await reader.cancel(); return null; }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(bytes);
}
export default { async fetch(request, env) {
  if (request.method !== 'POST' || new URL(request.url).pathname !== '/ingest') return reply(404);
  try {
    if (!env.GATEWAY_SECRET || request.headers.get('Content-Type') !== 'application/json') return reply(403);
    const body = await limitedBody(request); if (body === null) return reply(413);
    const stamp = request.headers.get('X-G1B2-Time') || '';
    const nonce = request.headers.get('X-G1B2-Nonce') || '';
    const signature = request.headers.get('X-G1B2-Signature') || '';
    if (request.headers.get('X-G1B2-Key') !== 'synthetic' ||
        !/^\d{1,12}$/.test(stamp) || Math.abs(Number(stamp) - Math.floor(Date.now() / 1000)) > 30 ||
        !id.test(nonce) || !hex.test(signature)) return reply(401);
    if (!equal(signature, await hmac(env.GATEWAY_SECRET, `${stamp}\n${nonce}\n${body}`))) return reply(401);
    const item = JSON.parse(body);
    if (!item || typeof item !== 'object' || Array.isArray(item) ||
        Object.keys(item).sort().join(',') !== 'digest,event_id,payload,sequence,session_id' ||
        !id.test(item.event_id) || typeof item.session_id !== 'string' ||
        !/^[A-Za-z0-9._:-]{1,128}$/.test(item.session_id) ||
        !Number.isSafeInteger(item.sequence) || item.sequence < 0 || !hex.test(item.digest) ||
        typeof item.payload !== 'string' || encoder.encode(item.payload).byteLength > 4096 ||
        !equal(item.digest, await sha256(item.payload))) return reply(422);
    const event = JSON.parse(item.payload);
    if (event.schema_version !== '1.0' || event.event_id !== item.event_id ||
        event.session_id !== item.session_id || (event.sequence ?? 0) !== item.sequence) return reply(422);
    try {
      await env.DB.prepare('INSERT INTO gateway_nonces VALUES (?,?)').bind(nonce, Number(stamp) + 30).run();
    } catch (error) {
      if (/unique constraint/i.test(String(error))) return reply(409);
      throw error;
    }
    if (request.headers.get('X-G1B3-Test-Fault') === '429') return reply(429);
    const stored = await env.DB.prepare('SELECT digest FROM gateway_receipts WHERE event_id=?')
      .bind(item.event_id).first();
    if (stored) return equal(stored.digest, item.digest) ?
      reply(200, { event_id: item.event_id, digest: item.digest }) : reply(409);
    try {
      await env.DB.prepare('INSERT INTO gateway_receipts VALUES (?,?)')
        .bind(item.event_id, item.digest).run();
    } catch (error) {
      if (!/unique constraint/i.test(String(error))) throw error;
      const winner = await env.DB.prepare('SELECT digest FROM gateway_receipts WHERE event_id=?')
        .bind(item.event_id).first();
      if (!winner || !equal(winner.digest, item.digest)) return reply(409);
    }
    return reply(200, { event_id: item.event_id, digest: item.digest });
  } catch { return reply(503); }
} };
