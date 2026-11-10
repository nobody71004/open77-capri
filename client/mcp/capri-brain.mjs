#!/usr/bin/env node
// Capri Brain: a local OpenAI-compatible endpoint for Capri's "local" provider.
//
// CapriVoz relays http:// provider calls from the game to this server, so the
// Cyberpunk process never has to make an insecure localhost request itself.
// The server forwards to Ollama by default, or to any OpenAI-compatible backend
// when CAPRI_BRAIN_BACKEND=openai. It never stores prompts or keys.
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
try {
  // Same optional key file as the MCP agent; a missing file is fine.
  process.loadEnvFile?.(path.join(MODULE_DIR, '..', '.env'));
} catch {
  // no local .env
}

const HOST = process.env.CAPRI_BRAIN_HOST || '127.0.0.1';
const PORT = Number(process.env.CAPRI_BRAIN_PORT || 8890);
const BACKEND = (process.env.CAPRI_BRAIN_BACKEND || 'ollama').toLowerCase();
const FREEBUFF_URL = 'https://freebuff.com/api/v1/paid';
const BACKEND_URL = (
  process.env.CAPRI_BRAIN_BACKEND_URL ||
  (BACKEND === 'openai'
    ? 'https://api.openai.com/v1'
    : BACKEND === 'freebuff'
      ? FREEBUFF_URL
      : 'http://127.0.0.1:11434/v1')
).replace(/\/+$/, '');
const MODEL =
  process.env.CAPRI_BRAIN_MODEL ||
  process.env.CAPRI_BRAIN_BACKEND_MODEL ||
  (BACKEND === 'openai'
    ? 'gpt-4.1-mini'
    : BACKEND === 'freebuff'
      ? process.env.OPENAI_MODEL || 'gpt-4o-mini'
      : 'qwen2.5:1.5b');
const API_KEY =
  process.env.CAPRI_BRAIN_API_KEY ||
  process.env.OPENAI_API_KEY ||
  '';
const MAX_TOKENS = clampInt(process.env.CAPRI_BRAIN_MAX_TOKENS || 260, 32, 2_000);
const TOKEN_PARAM = process.env.CAPRI_BRAIN_TOKEN_PARAM || 'max_tokens';
const VISION = process.env.CAPRI_BRAIN_VISION === '1';
const REQUEST_TIMEOUT_MS = clampInt(process.env.CAPRI_BRAIN_TIMEOUT_MS || 180_000, 5_000, 300_000);
const KEEP_ALIVE = process.env.CAPRI_BRAIN_KEEP_ALIVE || '30m';
const STARTED_AT = Date.now();

function clampInt(value, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return min;
  return Math.max(min, Math.min(Math.trunc(number), max));
}

function clampNumber(value, fallback, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.max(min, Math.min(number, max));
}

function sendJson(res, status, value) {
  const body = Buffer.from(JSON.stringify(value));
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': body.length,
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function readJsonBody(req, limit = 2_000_000) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new Error('request body too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      try {
        const raw = Buffer.concat(chunks).toString('utf8');
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(new Error(`invalid JSON: ${error.message}`));
      }
    });
    req.on('error', reject);
  });
}

function normalizeContent(content) {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return String(content ?? '');
  const parts = [];
  for (const part of content) {
    if (!part || typeof part !== 'object') continue;
    if (part.type === 'text') {
      parts.push({ type: 'text', text: String(part.text ?? '') });
    } else if (part.type === 'image_url') {
      if (VISION) {
        parts.push(part);
      } else {
        parts.push({ type: 'text', text: '[screenshot omitted by Capri Brain]' });
      }
    } else {
      parts.push({ type: 'text', text: `[${String(part.type || 'content')} omitted]` });
    }
  }
  if (parts.length === 0) return '';
  if (parts.every((part) => part.type === 'text')) {
    return parts.map((part) => part.text).join('\n');
  }
  return parts;
}

function normalizeMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error('messages must be a non-empty array');
  }
  return messages
    .filter((message) => message && typeof message === 'object')
    .map((message) => ({
      role: ['system', 'user', 'assistant', 'tool'].includes(message.role)
        ? message.role
        : 'user',
      content: normalizeContent(message.content),
    }))
    .filter((message) => (typeof message.content === 'string' ? message.content.length > 0 : true));
}

function backendHeaders() {
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (API_KEY) headers.Authorization = `Bearer ${API_KEY}`;
  return headers;
}

function backendModelFor(requested) {
  const model = String(requested || '').trim();
  if (!model || model === 'capri-brain') return MODEL;
  return model;
}

async function backendModels(timeoutMs = 2_000) {
  try {
    const response = await fetch(`${BACKEND_URL}/models`, {
      headers: backendHeaders(),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return { ok: false, status: response.status, data: null };
    return { ok: true, status: response.status, data: await response.json() };
  } catch (error) {
    return { ok: false, error: error.message, data: null };
  }
}

async function health() {
  const models = await backendModels(1_500);
  const ids = Array.isArray(models.data?.data)
    ? models.data.data.map((item) => item?.id).filter(Boolean).slice(0, 20)
    : [];
  return {
    ok: true,
    service: 'capri-brain',
    backend: BACKEND,
    backendUrl: BACKEND_URL,
    backendOk: models.ok,
    backendError: models.ok ? null : models.error || `HTTP ${models.status}`,
    model: MODEL,
    models: ids,
    vision: VISION,
    port: PORT,
    uptimeSeconds: Math.round((Date.now() - STARTED_AT) / 1000),
    hasBackendKey: Boolean(API_KEY),
  };
}

async function chat(req, res) {
  let body;
  try {
    body = await readJsonBody(req);
  } catch (error) {
    sendJson(res, 400, { error: { message: error.message, type: 'invalid_request_error' } });
    return;
  }

  let messages;
  try {
    messages = normalizeMessages(body.messages);
  } catch (error) {
    sendJson(res, 400, { error: { message: error.message, type: 'invalid_request_error' } });
    return;
  }

  const payload = {
    model: backendModelFor(body.model),
    messages,
    stream: false,
    temperature: clampNumber(body.temperature, 0.85, 0, 2),
    top_p: clampNumber(body.top_p, 0.95, 0, 1),
  };
  payload[TOKEN_PARAM] = clampInt(body.max_tokens ?? body.max_completion_tokens ?? MAX_TOKENS, 16, MAX_TOKENS);
  if (BACKEND === 'ollama') payload.keep_alive = KEEP_ALIVE;

  let upstream;
  try {
    upstream = await fetch(`${BACKEND_URL}/chat/completions`, {
      method: 'POST',
      headers: backendHeaders(),
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    sendJson(res, 502, {
      error: {
        message: `Capri Brain could not reach ${BACKEND} at ${BACKEND_URL}: ${error.message}`,
        type: 'backend_unreachable',
      },
    });
    return;
  }

  const raw = await upstream.text();
  if (!upstream.ok) {
    sendJson(res, upstream.status >= 400 ? upstream.status : 502, {
      error: {
        message: `Capri Brain backend HTTP ${upstream.status}: ${raw.slice(0, 1_200)}`,
        type: 'backend_error',
      },
    });
    return;
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    sendJson(res, 502, {
      error: {
        message: `Capri Brain backend returned non-JSON: ${raw.slice(0, 500)}`,
        type: 'backend_error',
      },
    });
    return;
  }
  sendJson(res, 200, data);
}

async function models(res) {
  const upstream = await backendModels(2_000);
  const ids = new Set(['capri-brain', MODEL]);
  if (Array.isArray(upstream.data?.data)) {
    for (const item of upstream.data.data) {
      if (item?.id) ids.add(item.id);
    }
  }
  sendJson(res, 200, {
    object: 'list',
    data: [...ids].map((id) => ({
      id,
      object: 'model',
      created: Math.floor(STARTED_AT / 1000),
      owned_by: 'capri-brain',
    })),
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || `${HOST}:${PORT}`}`);
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'authorization, content-type',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    });
    res.end();
    return;
  }

  try {
    if (req.method === 'GET' && (url.pathname === '/health' || url.pathname === '/')) {
      sendJson(res, 200, await health());
      return;
    }
    if (req.method === 'GET' && (url.pathname === '/v1/models' || url.pathname === '/models')) {
      await models(res);
      return;
    }
    if (
      req.method === 'POST' &&
      (url.pathname === '/v1/chat/completions' || url.pathname === '/chat/completions')
    ) {
      await chat(req, res);
      return;
    }
    sendJson(res, 404, { error: { message: 'not found', type: 'not_found' } });
  } catch (error) {
    sendJson(res, 500, { error: { message: error.message, type: 'server_error' } });
  }
});

server.listen(PORT, HOST, () => {
  console.log(
    `[capri-brain] listening on http://${HOST}:${PORT} backend=${BACKEND} model=${MODEL} vision=${VISION}`,
  );
  if (BACKEND === 'freebuff' && !API_KEY) {
    console.log('[capri-brain] freebuff selected but no OPENAI_API_KEY is set');
  }
  console.log(`[capri-brain] backend=${BACKEND_URL} key=${API_KEY ? 'set' : 'not set'}`);
});

function shutdown(signal) {
  console.log(`[capri-brain] ${signal}; closing`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 2_000).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
