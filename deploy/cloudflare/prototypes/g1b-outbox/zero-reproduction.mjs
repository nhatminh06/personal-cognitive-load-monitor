import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { readFile } from 'node:fs/promises';
const mf = new Miniflare(convertV4MiniflareOptions({workers:[{name:'repro',modules:true,script:'export default {fetch(){return new Response("ok")}}',compatibilityDate:'2026-11-26',d1Databases:['DB']}]}));
try {
 const db=await mf.getD1Database('DB','repro');
 for(const file of ['../../migrations/0001_focus.sql','0001_outbox.sql']) {
  const sql=await readFile(new URL(file,import.meta.url),'utf8');
  await db.batch(sql.split(';').filter(s=>s.trim()).map(s=>db.prepare(s)));
 }
 await db.prepare("INSERT INTO sessions VALUES ('s','owner','study','behavioral',NULL,'session.started',1,'t','t',0)").run();
 for(const n of [1,2]) {
  try {
   await db.batch([
    db.prepare("INSERT INTO events VALUES (?,?,'s','effort.reported','t',0,'{}',?,NULL,NULL)").bind(`e${n}`,`k${n}`,`l${n}`),
    db.prepare("INSERT INTO outbox(event_id,session_id,sequence,owner_id,payload,digest,state) VALUES (?,'s',0,'owner','{}','digest','pending')").bind(`e${n}`),
   ]);
   console.log(`event ${n} committed`);
  } catch(e) { console.log(`event ${n} rejected: ${e.message}`); }
 }
 console.log(await db.prepare('SELECT (SELECT count(*) FROM events) AS events,(SELECT count(*) FROM outbox) AS outbox').first());
} finally {await mf.dispose();}
