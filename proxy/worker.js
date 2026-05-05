/**
 * Cloudflare Worker proxy: GH Pages -> HF Space.
 *
 * Holds HF_TOKEN as a Cloudflare secret (set via: wrangler secret put HF_TOKEN).
 * Public clients post { message: string } to /chat; we call the Space's
 * Gradio 5 ChatInterface and return { final_answer, tool_calls }.
 * No tokens are ever exposed to the browser.
 */

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

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    const url = new URL(request.url);
    if (url.pathname !== '/chat' || request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'POST /chat with { message }' }), {
        status: 404,
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
  },
};
