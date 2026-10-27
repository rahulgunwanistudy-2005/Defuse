import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

// Keep API requests on the console's origin in development and in the deployed build.
// Passing the response stream through preserves SSE delivery without buffering it.
export const GET: RequestHandler = async ({ url, request }) => {
  const base = env.DEFUSE_API_BASE ?? env.DEFUSE_API ?? 'http://127.0.0.1:8000';
  const headers = new Headers({ accept: request.headers.get('accept') ?? 'application/json' });
  const cursor = request.headers.get('last-event-id');
  if (cursor) headers.set('last-event-id', cursor);
  try {
    const upstream = await fetch(base.replace(/\/$/, '') + url.pathname + url.search, {
      headers,
      signal: request.signal
    });
    const responseHeaders = new Headers();
    for (const name of ['content-type', 'cache-control', 'x-accel-buffering']) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return new Response('Engine unavailable. Check the engine service and DEFUSE_API_BASE.', {
      status: 502
    });
  }
};
