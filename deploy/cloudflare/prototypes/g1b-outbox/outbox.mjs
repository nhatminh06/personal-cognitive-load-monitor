import { createHash } from 'node:crypto';

const digest = value => createHash('sha256').update(value).digest('hex');
const canonical = value => JSON.stringify(Object.keys(value).filter(key => key !== 'ingested_at')
  .sort().map(key => [key, value[key]]));
const row = (db, sql, ...args) => db.prepare(sql).bind(...args).first();
const all = async (db, sql, ...args) => (await db.prepare(sql).bind(...args).all()).results;
const statement = (db, sql, ...args) => db.prepare(sql).bind(...args);

export async function append(db, event, owner) {
  const lifecycle = ['session.started', 'session.paused', 'session.resumed',
    'session.completed', 'session.cancelled'].includes(event.event_type);
  const sequence = event.sequence ?? 0;
  if (lifecycle ? !Number.isSafeInteger(sequence) || sequence < 1 :
      !['behavioral.window', 'effort.reported'].includes(event.event_type) || sequence !== 0) {
    throw new Error('invalid event sequence or type');
  }
  const payload = JSON.stringify(event);
  const existing = await all(db, `SELECT e.event_id,e.idempotency_key,e.event_json,s.owner_id
    FROM events e JOIN sessions s USING(session_id)
    WHERE e.event_id=? OR e.idempotency_key=?`, event.event_id, event.idempotency_key);
  if (existing.length) {
    if (existing.length !== 1 || existing[0].event_id !== event.event_id ||
        existing[0].idempotency_key !== event.idempotency_key ||
        existing[0].owner_id !== owner ||
        canonical(JSON.parse(existing[0].event_json)) !== canonical(event)) {
      throw new Error('event identity conflict');
    }
    const delivery = await row(db, 'SELECT digest FROM outbox WHERE event_id=?', event.event_id);
    if (!delivery || delivery.digest !== digest(existing[0].event_json)) {
      throw new Error('committed event lacks matching outbox');
    }
    return false;
  }
  const create = lifecycle && sequence === 1;
  const statements = create ? [statement(db,
    `INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,0)`, event.session_id, owner,
    event.session_kind, event.privacy_mode, null, event.event_type, 1,
    event.event_time, event.ingested_at)] : !lifecycle ? [
    statement(db, `UPDATE sessions SET version=version+1 WHERE session_id=? AND owner_id=?`,
      event.session_id, owner),
    statement(db, 'INSERT INTO cas_guard VALUES (changes())'),
    statement(db, 'DELETE FROM cas_guard'),
  ] : [
    statement(db, `UPDATE sessions SET state=?,last_sequence=?,last_event_time=?,version=version+1
      WHERE session_id=? AND owner_id=? AND last_sequence=?`, event.event_type,
      event.sequence, event.event_time, event.session_id, owner, event.sequence - 1),
    statement(db, 'INSERT INTO cas_guard VALUES (changes())'),
    statement(db, 'DELETE FROM cas_guard'),
  ];
  statements.push(statement(db, 'INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)',
    event.event_id, event.idempotency_key, event.session_id, event.event_type,
    event.event_time, sequence, payload, event.label_id ?? null,
    event.window_id ?? null, event.reported_at ?? null));
  statements.push(statement(db, `INSERT INTO outbox
    (event_id,session_id,sequence,owner_id,payload,digest,state)
    VALUES (?,?,?,?,?,?,'pending')`, event.event_id, event.session_id,
    sequence, owner, payload, digest(payload)));
  try { await db.batch(statements); return true; }
  catch (error) {
    // A concurrent identical insert can win after the first lookup.
    if (/unique constraint/i.test(String(error))) {
      const winner = await all(db, `SELECT e.event_id,e.idempotency_key,e.event_json,s.owner_id
        FROM events e JOIN sessions s USING(session_id)
        WHERE e.event_id=? OR e.idempotency_key=?`, event.event_id, event.idempotency_key);
      if (winner.length === 1 && winner[0].event_id === event.event_id &&
          winner[0].idempotency_key === event.idempotency_key &&
          winner[0].owner_id === owner &&
          canonical(JSON.parse(winner[0].event_json)) === canonical(event)) {
        const delivery = await row(db, 'SELECT digest FROM outbox WHERE event_id=?', event.event_id);
        if (!delivery || delivery.digest !== digest(winner[0].event_json)) {
          throw new Error('committed event lacks matching outbox');
        }
        return false;
      }
    }
    throw error;
  }
}

export async function claim(db, now, token, leaseSeconds = 10) {
  if (!token || leaseSeconds < 1) throw new Error('invalid lease');
  // Commit order serializes all session events, including repeated sequence zero.
  return row(db, `UPDATE outbox SET state='leased',lease_token=?,lease_until=?,attempts=attempts+1
    WHERE event_id=(SELECT o.event_id FROM outbox o
      WHERE ((o.state IN ('pending','retry') AND o.next_attempt_at<=?)
        OR (o.state='leased' AND o.lease_until<=?))
      AND NOT EXISTS (SELECT 1 FROM outbox p WHERE p.session_id=o.session_id
        AND p.delivery_order<o.delivery_order AND p.state!='acknowledged')
      ORDER BY o.delivery_order LIMIT 1)
    AND ((state IN ('pending','retry') AND next_attempt_at<=?)
      OR (state='leased' AND lease_until<=?))
    RETURNING *`, token, now + leaseSeconds, now, now, now, now);
}

export async function acknowledge(db, eventId, token, ack, now) {
  if (ack?.event_id !== eventId || !/^[0-9a-f]{64}$/.test(ack?.digest || '')) return false;
  const result = await row(db, `UPDATE outbox SET state='acknowledged',lease_token=NULL,
    lease_until=NULL,acknowledged_at=?,error_class=NULL
    WHERE event_id=? AND state='leased' AND lease_token=? AND lease_until>?
    AND digest=? RETURNING event_id`, now, eventId, token, now, ack.digest);
  return !!result;
}

export async function reject(db, eventId, token, errorClass, now, terminal = false) {
  const current = await row(db, `SELECT attempts FROM outbox
    WHERE event_id=? AND state='leased' AND lease_token=? AND lease_until>?`, eventId, token, now);
  if (!current) return false;
  const dead = terminal || current.attempts >= 3;
  const delay = Math.min(60, 2 ** current.attempts);
  const result = await row(db, `UPDATE outbox SET state=?,lease_token=NULL,lease_until=NULL,
    next_attempt_at=?,error_class=? WHERE event_id=? AND state='leased'
    AND lease_token=? AND lease_until>? AND attempts=? RETURNING event_id`, dead ? 'dead' : 'retry',
    now + delay, errorClass, eventId, token, now, current.attempts);
  return !!result;
}

export class MockGateway {
  constructor() { this.records = new Map(); this.attempts = []; }
  deliver(delivery, mode = 'ok') {
    if (mode === 'unavailable' || mode === 'timeout') throw new Error(mode);
    this.attempts.push(delivery.event_id);
    const old = this.records.get(delivery.event_id);
    if (old && old.digest !== delivery.digest) throw new Error('conflicting duplicate');
    this.records.set(delivery.event_id, { digest: delivery.digest, session_id: delivery.session_id });
    if (mode === 'lost_ack') throw new Error('lost_ack');
    return { event_id: delivery.event_id, digest: delivery.digest };
  }
}

export async function dispatch(db, gateway, now, token, mode = 'ok') {
  const delivery = await claim(db, now, token);
  if (!delivery) return null;
  if (mode === 'crash_after_lease') return delivery;
  try {
    const ack = gateway.deliver(delivery, mode);
    if (mode === 'crash_before_mark') return delivery;
    if (!await acknowledge(db, delivery.event_id, token, ack, now)) throw new Error('invalid_ack');
  } catch (error) {
    if (mode === 'crash_before_mark') throw error;
    await reject(db, delivery.event_id, token, String(error.message), now,
      error.message === 'conflicting duplicate' || error.message === 'invalid_ack');
  }
  return delivery;
}

export async function reconcile(db, gateway) {
  const rows = await all(db, 'SELECT event_id,state,digest FROM outbox ORDER BY delivery_order');
  const missing = rows.filter(r => !gateway.records.has(r.event_id)).map(r => r.event_id);
  const orphaned = [...gateway.records.keys()].filter(id => !rows.some(r => r.event_id === id));
  const duplicateAttempts = [...new Set(gateway.attempts.filter((id, i, a) => a.indexOf(id) !== i))];
  const mismatched = rows.filter(r => gateway.records.has(r.event_id) &&
    gateway.records.get(r.event_id).digest !== r.digest).map(r => r.event_id);
  return { missing, orphaned, duplicateAttempts, mismatched,
    unacknowledged: rows.filter(r => r.state !== 'acknowledged').map(r => r.event_id) };
}
