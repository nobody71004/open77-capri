// The brain as players' games reach it: a real capri-brain.mjs process, a stand-in backend that counts what reaches
// the model. Run: node --test client/mcp/capri-brain.test.mjs
import { spawn } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BRAIN = process.env.CAPRI_BRAIN_FILE || path.join(HERE, 'capri-brain.mjs');
// What a Capri build with Mass Override lists in its system prompt (Capri.Actions.reds).
const SYSTEM = 'You are Capri.\n {"do":"mass_override","target":...} change everything around V at once\n';
const BANTER = '{"say":"Well, well, V. Showing off, are we?","mood":"teasing","face":"smile"}';

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
}

async function freePort() {
  const s = http.createServer();
  const port = await listen(s);
  await new Promise((r) => s.close(r));
  return port;
}

async function start() {
  const backend = { calls: 0, reply: BANTER };
  const fake = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      if (req.url.endsWith('/models')) {
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ data: [{ id: 'qwen2.5:7b' }] }));
        return;
      }
      backend.calls += 1;
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ choices: [{ index: 0, message: { role: 'assistant', content: backend.reply } }] }));
    });
  });
  const backendPort = await listen(fake);
  const port = await freePort();
  const lines = [];
  const child = spawn(process.execPath, [BRAIN], {
    env: {
      ...process.env,
      CAPRI_BRAIN_PORT: String(port),
      CAPRI_BRAIN_BACKEND: 'openai',
      CAPRI_BRAIN_BACKEND_URL: `http://127.0.0.1:${backendPort}/v1`,
      CAPRI_BRAIN_MODEL: 'qwen2.5:7b',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  for (const stream of [child.stdout, child.stderr]) {
    stream.on('data', (d) => lines.push(...String(d).split('\n').filter(Boolean)));
  }
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 100; i += 1) {
    try {
      const r = await fetch(`${base}/health`);
      if (r.ok) break;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  return {
    base,
    backend,
    lines,
    async ask(said, system = SYSTEM) {
      const messages = [{ role: 'user', content: said }];
      if (system) messages.unshift({ role: 'system', content: system });
      const t0 = Date.now();
      const r = await fetch(`${base}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ model: 'capri-brain', messages }),
      });
      const body = await r.json();
      return { status: r.status, ms: Date.now() - t0, reply: JSON.parse(body.choices[0].message.content) };
    },
    async stop() {
      child.kill('SIGTERM');
      await new Promise((r) => child.once('exit', r));
      await new Promise((r) => fake.close(r));
    },
  };
}

test('every way players type Mass Override casts at once, without the model', async () => {
  const b = await start();
  try {
    for (const said of [
      'mass over ride',
      'Mass Over Ride',
      'MASS OVERRIDE',
      'mass override',
      'massoverride',
      'mass-override',
      'mass over-ride',
      'mass_override',
      'mass overide',
      'mass overrride',
      'mass ovverride',
      'mas override',
      'mass overrid',
      'Capri, Mass Override — lights, screens and cars around me',
      'capri do a mass over ride now',
      'change everything around me',
      'V says: mass over ride',
    ]) {
      const before = b.backend.calls;
      const { status, ms, reply } = await b.ask(said);
      assert.equal(status, 200, said);
      assert.equal(b.backend.calls, before, `the model was asked for "${said}"`);
      assert.deepEqual(reply.actions.map((a) => a.do), ['mass_override'], said);
      assert.equal(reply.say, 'Mass Override, V.', said);
      assert.ok(ms < 2_000, `${said}: ${ms} ms`);
    }
  } finally {
    await b.stop();
  }
});

test('a mode word pins the mode first', async () => {
  const b = await start();
  try {
    const { reply } = await b.ask('mass over ride blackout');
    assert.deepEqual(reply.actions, [{ do: 'mass_override_mode', target: 'blackout' }, { do: 'mass_override' }]);
    assert.equal(reply.say, 'Mass Override, blackout, V.');
  } finally {
    await b.stop();
  }
});

test('everything else goes to the model, untouched', async () => {
  const b = await start();
  try {
    for (const said of [
      'what is the mass of the sun',
      'that was a massive overreaction',
      'park the car over there',
      'put the radio on, then overdrive',
      'stop overriding my settings',
      'mass over riding a bike',
      'override the door',
      'hello Capri',
    ]) {
      const before = b.backend.calls;
      const { status, reply } = await b.ask(said);
      assert.equal(status, 200, said);
      assert.equal(b.backend.calls, before + 1, `"${said}" did not reach the model`);
      assert.equal(reply.actions, undefined, said);
      assert.equal(reply.say, 'Well, well, V. Showing off, are we?', said);
    }
  } finally {
    await b.stop();
  }
});

test('a Capri build without Mass Override is never sent one', async () => {
  const b = await start();
  try {
    const before = b.backend.calls;
    const { reply } = await b.ask('mass over ride', 'You are Capri. Actions: ping, honk.');
    assert.equal(b.backend.calls, before + 1);
    assert.equal(reply.actions, undefined);
  } finally {
    await b.stop();
  }
});

test('the logs say which way each request went, never what V said', async () => {
  const b = await start();
  try {
    await b.ask('mass over ride');
    await b.ask('hello Capri');
    b.backend.reply = '{"say":"Here goes.","actions":[{"do":"mass_override"}]}';
    await b.ask('make the whole block go dark');
    const health = await (await fetch(`${b.base}/health`)).json();
    assert.match(health.build, /^2026-11-12\.1/);
    await new Promise((r) => setTimeout(r, 100));
    const text = b.lines.join('\n');
    assert.match(text, /\[capri-brain\] build 2026-11-12\.1 .*listening/);
    assert.match(text, /\[capri-brain\] mass_override shortcut \(no model call\) actions=\[\{"do":"mass_override"\}\] saidChars=14/);
    assert.match(text, /\[capri-brain\] chat messages=2\/2 .* status=200 ms=\d+ mo=no/);
    assert.match(text, /\[capri-brain\] chat messages=2\/2 .* status=200 ms=\d+ mo=model/);
    for (const said of ['mass over ride', 'hello Capri', 'whole block']) {
      assert.ok(!text.includes(said), `the log holds "${said}"`);
    }
  } finally {
    await b.stop();
  }
});
