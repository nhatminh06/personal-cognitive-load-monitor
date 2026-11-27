// Isolated Worker-compatible G1B.2 prototype; never deploy this file.
const encoder = new TextEncoder();
const row = (db, sql, ...args) => db.prepare(sql).bind(...args).first();
const maxItemsCap = 5, maxBytesCap = 8192;

async function signature(secret, stamp, nonce, body) {
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const bytes = await crypto.subtle.sign('HMAC', key, encoder.encode(`${stamp}\n${nonce}\n${body}`));
  return Array.from(new Uint8Array(bytes), x => x.toString(16).padStart(2, '0')).join('');
}

async function claim(db, now, token) {
  // Commit order serializes all session events, including repeated sequence zero.
  return row(db, `UPDATE outbox SET state='leased',lease_token=?,lease_until=?,attempts=attempts+1
    WHERE event_id=(SELECT o.event_id FROM outbox o
      WHERE ((o.state IN ('pending','retry') AND o.next_attempt_at<=?)
        OR (o.state='leased' AND o.lease_until<=?))
      AND NOT EXISTS (SELECT 1 FROM outbox p WHERE p.session_id=o.session_id
        AND p.delivery_order<o.delivery_order AND p.state!='acknowledged')
      ORDER BY o.delivery_order LIMIT 1)
    AND ((state IN ('pending','retry') AND next_attempt_at<=?)
      OR (state='leased' AND lease_until<=?)) RETURNING *`,
    token, now + 10, now, now, now, now);
}

async function release(db, delivery, token, now) {
  return row(db, `UPDATE outbox SET state='pending',lease_token=NULL,lease_until=NULL,
    attempts=attempts-1 WHERE event_id=? AND state='leased' AND lease_token=?
    AND lease_until>? RETURNING event_id`, delivery.event_id, token, now);
}

async function acknowledge(db, delivery, token, ack, now) {
  if (ack?.event_id !== delivery.event_id || ack?.digest !== delivery.digest) return false;
  return !!await row(db, `UPDATE outbox SET state='acknowledged',lease_token=NULL,
    lease_until=NULL,acknowledged_at=?,error_class=NULL WHERE event_id=?
    AND state='leased' AND lease_token=? AND lease_until>? AND digest=? RETURNING event_id`,
    now, delivery.event_id, token, now, delivery.digest);
}

async function reject(db, delivery, token, errorClass, now, terminal = false) {
  const dead = terminal || delivery.attempts >= 3;
  return !!await row(db, `UPDATE outbox SET state=?,lease_token=NULL,lease_until=NULL,
    next_attempt_at=?,error_class=? WHERE event_id=? AND state='leased'
    AND lease_token=? AND lease_until>? AND attempts=? RETURNING event_id`,
    dead ? 'dead' : 'retry', now + Math.min(60, 2 ** delivery.attempts),
    errorClass, delivery.event_id, token, now, delivery.attempts);
}

export async function dispatchBatch(env, options = {}) {
  const currentTime = () => options.now ?? Math.floor(Date.now() / 1000);
  const now = currentTime();
  const maxItems = options.maxItems ?? 1, maxBytes = options.maxBytes ?? 4096;
  const timeoutMs = options.timeoutMs ?? 2000;
  const keyId = env.GATEWAY_KEY_ID ?? 'synthetic';
  if (!Number.isSafeInteger(now) || !Number.isInteger(maxItems) || maxItems < 1 ||
      maxItems > maxItemsCap || !Number.isInteger(maxBytes) || maxBytes < 1 ||
      maxBytes > maxBytesCap || !Number.isInteger(timeoutMs) || timeoutMs < 1 ||
      timeoutMs > 5000 || !env.GATEWAY_SECRET || !env.GATEWAY_URL ||
      !/^[A-Za-z0-9._:-]{1,64}$/.test(keyId) ||
      (env.GATEWAY_REQUIRE_HTTPS === 'true' && !env.GATEWAY_URL.startsWith('https://'))) {
    throw new Error('invalid dispatcher configuration');
  }
  const counts = { claimed: 0, delivered: 0, retried: 0, dead: 0, bytes: 0,
    d1Operations: 0, httpRequests: 0 };
  const started = performance.now();
  for (let i = 0; i < maxItems; i++) {
    if (options.signal?.aborted) break;
    const token = crypto.randomUUID();
    const delivery = await claim(env.DB, now, token); counts.d1Operations++;
    if (!delivery) break;
    const size = encoder.encode(delivery.payload).byteLength;
    if (size > maxBytes) {
      if (!await reject(env.DB, delivery, token, 'payload_limit', currentTime(), true)) {
        throw new Error('lease lost');
      }
      counts.d1Operations++; counts.dead++; break;
    }
    if (counts.bytes + size > maxBytes) {
      if (!await release(env.DB, delivery, token, currentTime())) throw new Error('lease lost');
      counts.d1Operations++; break;
    }
    counts.claimed++; counts.bytes += size;
    if (options.fault === 'crash_after_lease') break;
    const body = JSON.stringify({ event_id: delivery.event_id, session_id: delivery.session_id,
      sequence: delivery.sequence, digest: delivery.digest, payload: delivery.payload });
    const stamp = String(now), nonce = crypto.randomUUID();
    const mac = await signature(env.GATEWAY_SECRET, stamp, nonce, body);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abort = () => controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    try {
      if (options.signal?.aborted) throw new Error('cancelled');
      counts.httpRequests++;
      const outbound = env.GATEWAY?.fetch ? env.GATEWAY.fetch.bind(env.GATEWAY) : fetch;
      const response = await outbound(env.GATEWAY_URL, { method: 'POST', body,
        signal: controller.signal, headers: { 'Content-Type': 'application/json',
          'X-G1B2-Key': keyId, 'X-G1B2-Time': stamp, 'X-G1B2-Nonce': nonce,
          'X-G1B2-Signature': options.fault === 'bad_sig' ? '0'.repeat(64) : mac,
          ...(options.fault === 'retry_429' ? { 'X-G1B3-Test-Fault': '429' } : {}) } });
      if (!response.ok) {
        const terminal = [400, 401, 403, 409, 413, 422].includes(response.status);
        if (!await reject(env.DB, delivery, token, `http_${response.status}`,
          currentTime(), terminal)) throw new Error('lease lost');
        counts.d1Operations++; counts[terminal ? 'dead' : 'retried']++; break;
      }
      const ack = await response.json();
      if (options.fault === 'crash_before_mark') break;
      if (!await acknowledge(env.DB, delivery, token, ack, currentTime())) {
        if (!await reject(env.DB, delivery, token, 'invalid_ack', currentTime(), true)) {
          throw new Error('lease lost');
        }
        counts.d1Operations += 2; counts.dead++; break;
      }
      counts.d1Operations++; counts.delivered++;
    } catch (error) {
      const kind = options.signal?.aborted ? 'cancelled' :
        controller.signal.aborted ? 'timeout' : 'gateway_unavailable';
      if (!await reject(env.DB, delivery, token, kind, currentTime())) {
        throw new Error('lease lost');
      }
      counts.d1Operations++; counts.retried++; break;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', abort);
    }
  }
  return { ...counts, wallMs: performance.now() - started };
}

export async function inspectDead(db, limit = 20) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new Error('invalid limit');
  return (await db.prepare(`SELECT event_id,session_id,attempts,error_class
    FROM outbox WHERE state='dead' ORDER BY delivery_order LIMIT ?`).bind(limit).all()).results;
}

export async function reconcile(db, acceptedIds, attemptIds, limit = 100) {
  if (!Array.isArray(acceptedIds) || !Array.isArray(attemptIds) ||
      acceptedIds.length > 100 || attemptIds.length > 100 || !Number.isInteger(limit) ||
      limit < 1 || limit > 100 || [...acceptedIds, ...attemptIds].some(x => typeof x !== 'string')) {
    throw new Error('invalid reconciliation input');
  }
  const rows = (await db.prepare('SELECT event_id,state,digest FROM outbox ORDER BY delivery_order LIMIT ?')
    .bind(limit + 1).all()).results;
  const truncated = rows.length > limit;
  const page = rows.slice(0, limit), known = new Set(page.map(x => x.event_id));
  const accepted = new Set(acceptedIds);
  return { missing: page.filter(x => !accepted.has(x.event_id)).map(x => x.event_id),
    orphaned: truncated ? [] : acceptedIds.filter(x => !known.has(x)),
    unverifiedAccepted: truncated ? acceptedIds.filter(x => !known.has(x)) : [],
    duplicateAttempts: [...new Set(attemptIds.filter((id, i) => attemptIds.indexOf(id) !== i))],
    unacknowledged: page.filter(x => x.state !== 'acknowledged').map(x => x.event_id),
    truncated };
}
