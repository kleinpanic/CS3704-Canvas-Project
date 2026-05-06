/**
 * Cloudflare Worker proxy: GH Pages -> HF Space + Canvas API.
 *
 * Secrets (set via wrangler secret put):
 *   HF_TOKEN     — HuggingFace token for the demo Space
 *   CANVAS_TOKEN — Canvas API token for live iframe calls
 *
 * Routes:
 *   POST /chat   — proxy to HF Space, returns { final_answer, tool_calls }
 *   POST /canvas — proxy to canvas.vt.edu, returns Canvas API JSON
 *
 * No tokens are ever exposed to the browser.
 */

// Defense-in-depth PII scrub for Canvas API responses. The live demo does not
// currently route through /canvas, but if it ever does, PII won't leak.
const _EMAIL_RE = /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g;
const _PHONE_RE = /\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g;
const _SSN_RE   = /\b\d{3}-\d{2}-\d{4}\b/g;
const _ADDR_RE  = /\b\d{1,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Court|Ct|Lane|Ln)\b/g;

function scrubString(s) {
  return s
    .replace(_SSN_RE,   '[SSN]')
    .replace(_EMAIL_RE, '[EMAIL]')
    .replace(_PHONE_RE, '[PHONE]')
    .replace(_ADDR_RE,  '[ADDRESS]');
}

function scrubJson(obj) {
  if (typeof obj === 'string') return scrubString(obj);
  if (Array.isArray(obj)) return obj.map(scrubJson);
  if (obj !== null && typeof obj === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(obj)) out[k] = scrubJson(v);
    return out;
  }
  return obj;
}

const SPACE_BASE = 'https://kleinpanic93-canvas-calendar-agent-demo.hf.space';
const ALLOWED_ORIGINS = [
  'https://kleinpanic.github.io',
  'http://localhost:8000',
  'http://127.0.0.1:8000',
];

function corsHeaders(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function parseMarkdownToolLines(block) {
  const lineRe = /^-\s*`([\w.]+)\((\{[^`]*\})\)`\s*->\s*`([^`]*)`/gm;
  const out = [];
  for (const m of block.matchAll(lineRe)) {
    let args = {};
    try { args = JSON.parse(m[2]); } catch (_) {}
    let result = m[3].replace(/\.\.\.$/, '');
    try { result = JSON.parse(result); } catch (_) { /* keep preview */ }
    out.push({ tool: m[1], args, result });
  }
  return out;
}

async function callSpace(message, env) {
  const post = await fetch(`${SPACE_BASE}/gradio_api/call/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.HF_TOKEN}`,
    },
    body: JSON.stringify({ data: [message, []] }),
  });
  if (!post.ok) throw new Error(`Space POST: HTTP ${post.status}`);
  const postJson = await post.json();
  const eid = postJson.event_id;
  if (!eid) throw new Error('No event_id from Space');

  const stream = await fetch(`${SPACE_BASE}/gradio_api/call/chat/${eid}`, {
    headers: { 'Authorization': `Bearer ${env.HF_TOKEN}` },
  });
  if (!stream.ok) throw new Error(`Space stream: HTTP ${stream.status}`);
  const text = await stream.text();
  const completeMatch = text.match(/event:\s*complete\s*\ndata:\s*(.+)/);
  if (!completeMatch) {
    const errMatch = text.match(/event:\s*error\s*\ndata:\s*(.+)/);
    if (errMatch) throw new Error(`Space SSE error: ${errMatch[1]}`);
    throw new Error('Unexpected SSE format from Space');
  }
  const arr = JSON.parse(completeMatch[1]);
  const responseStr = Array.isArray(arr) ? arr[0] : arr;

  const toolBlock = responseStr.match(/^([\s\S]*?)\n*---\n\*\*Tool calls[^\n]*\*\*\n([\s\S]+)$/);
  if (toolBlock) {
    return {
      final_answer: toolBlock[1].trim(),
      tool_calls: parseMarkdownToolLines(toolBlock[2]),
    };
  }
  return { final_answer: responseStr, tool_calls: [] };
}

const CANVAS_BASE = 'https://canvas.vt.edu';
const ALLOWED_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

async function handleChat(request, env, cors) {
  if (request.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'POST /chat with { message }' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  let body;
  try { body = await request.json(); }
  catch (_) {
    return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }
  if (!body || typeof body.message !== 'string' || !body.message.trim()) {
    return new Response(JSON.stringify({ error: 'message is required' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }
  if (body.message.length > 4000) {
    return new Response(JSON.stringify({ error: 'message too long (max 4000 chars)' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  try {
    const out = await callSpace(body.message, env);
    return new Response(JSON.stringify(out), {
      status: 200,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err.message || err) }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }
}

async function handleCanvas(request, env, cors) {
  if (request.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'POST /canvas with { endpoint, method?, body? }' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  // PII bypass requires Authorization: Bearer <INTERNAL_PASSTHROUGH_TOKEN>.
  // Token must be set as a Cloudflare environment secret. Unset = no bypass possible.
  const authHeader = request.headers.get('Authorization') || '';
  const passToken = env.INTERNAL_PASSTHROUGH_TOKEN || '';
  const noPiiScrub = passToken !== '' && authHeader === `Bearer ${passToken}`;

  let body;
  try { body = await request.json(); }
  catch (_) {
    return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  const { endpoint, method = 'GET', body: canvasBody } = body || {};

  if (typeof endpoint !== 'string' || !endpoint.startsWith('/api/v1/')) {
    return new Response(JSON.stringify({ error: 'endpoint must start with /api/v1/' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  const upperMethod = String(method).toUpperCase();
  if (!ALLOWED_METHODS.has(upperMethod)) {
    return new Response(JSON.stringify({ error: `method must be one of: ${[...ALLOWED_METHODS].join(', ')}` }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  if (canvasBody !== undefined && JSON.stringify(canvasBody).length > 4000) {
    return new Response(JSON.stringify({ error: 'body too large (max 4000 chars serialized)' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  }

  const upstreamHeaders = {
    'Authorization': `Bearer ${env.CANVAS_TOKEN}`,
    'Accept': 'application/json',
  };
  const fetchInit = { method: upperMethod, headers: upstreamHeaders };
  if (canvasBody !== undefined && upperMethod !== 'GET') {
    fetchInit.headers['Content-Type'] = 'application/json';
    fetchInit.body = JSON.stringify(canvasBody);
  }

  const upstream = await fetch(`${CANVAS_BASE}${endpoint}`, fetchInit);
  const upstreamText = await upstream.text();
  const contentType = upstream.headers.get('Content-Type') || 'application/json';

  let responseBody = upstreamText;
  if (!noPiiScrub && upstream.ok && contentType.includes('application/json')) {
    try {
      const parsed = JSON.parse(upstreamText);
      responseBody = JSON.stringify(scrubJson(parsed));
    } catch (_) {
      // Non-parseable body — pass through as-is
    }
  }

  return new Response(responseBody, {
    status: upstream.status,
    headers: { 'Content-Type': contentType, ...cors },
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    const { pathname } = new URL(request.url);

    if (pathname === '/chat') return handleChat(request, env, cors);
    if (pathname === '/canvas') return handleCanvas(request, env, cors);

    return new Response(JSON.stringify({ error: 'Not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json', ...cors },
    });
  },
};
