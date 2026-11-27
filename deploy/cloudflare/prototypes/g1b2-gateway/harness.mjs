// Test-only HTTP hook for Miniflare; the dispatcher has no public route.
import { dispatchBatch } from './dispatcher.mjs';

export default { async fetch(request, env) {
  if (request.method !== 'POST' || new URL(request.url).pathname !== '/dispatch') {
    return new Response('Not found', { status: 404 });
  }
  try {
    const options = await request.json();
    return Response.json(await dispatchBatch(env, options));
  } catch {
    return Response.json({ error: 'dispatch unavailable' }, { status: 503 });
  }
} };
