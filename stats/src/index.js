// The reflip statistics endpoint: one counter per combination of allowed values, per day.
//
// It never reads the request's IP address, user agent, referrer or cookies, and it stores
// no row per visit: an event either adds one to an existing tally or is refused. Cloudflare
// still sees the connection, as any host does; the site's privacy page says so.

import { MAX_BODY, validate } from "./schema.js";

const ORIGIN = "https://nerln.github.io";

function cors(status, body = null) {
  return new Response(body, {
    status,
    headers: {
      "Access-Control-Allow-Origin": ORIGIN,
      "Access-Control-Allow-Methods": "POST",
      "Access-Control-Allow-Headers": "Content-Type",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function handle(request, env, today = new Date().toISOString().slice(0, 10)) {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return cors(204);
  if (request.method !== "POST" || url.pathname !== "/e") return cors(404);
  // Only the site may count. A request from anywhere else is answered and ignored, so the
  // counter cannot be filled by a script that has nothing to do with the site.
  if (request.headers.get("Origin") !== ORIGIN) return cors(403);
  const raw = await request.text();
  if (raw.length > MAX_BODY) return cors(413);
  let event;
  try {
    event = validate(JSON.parse(raw));
  } catch {
    event = null;
  }
  if (!event) return cors(400);
  await env.DB.prepare(
    "INSERT INTO counts (day, e, f, m, n) VALUES (?, ?, ?, ?, 1) " +
      "ON CONFLICT (day, e, f, m) DO UPDATE SET n = n + 1",
  )
    .bind(today, event.e, event.f, event.m)
    .run();
  return cors(204);
}

export default { fetch: (request, env) => handle(request, env) };
