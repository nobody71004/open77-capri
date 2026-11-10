const test = require("node:test");
const assert = require("node:assert/strict");
const { createDevServer } = require("./dev-server");

function start(options = {}) {
  let clock = 0;
  const server = createDevServer({ now: () => clock, ...options });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const base = `http://127.0.0.1:${server.address().port}`;
      resolve({
        base,
        advance: (ms) => {
          clock += ms;
        },
        close: () => new Promise((done) => server.close(done)),
      });
    });
  });
}

async function post(base, route, body) {
  const res = await fetch(`${base}${route}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: res.status, body: await res.json() };
}

const candidates = (n, prefix) =>
  Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i}`, type: "light", area: "Watson:4:2" }));

test("a cast over HTTP alternates the mode and reports the areas", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0, durationMs: 1000 });
  try {
    assert.equal((await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 })).status, 200);

    const first = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(3, "a") });
    assert.equal(first.status, 200);
    assert.equal(first.body.event.mode, "blackout", "the first cast is blackout");
    assert.deepEqual(first.body.event.areas, ["Watson:4:2"]);
    assert.equal(first.body.event.targets.length, 3);

    const second = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(3, "b") });
    assert.equal(second.body.event.mode, "blink", "the next cast flips");
  } finally {
    await srv.close();
  }
});

test("a pinned mode over HTTP holds across casts", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0, mode: "blackout" });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });
    const a = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "x") });
    const b = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "y") });
    assert.equal(a.body.event.mode, "blackout");
    assert.equal(b.body.event.mode, "blackout");
  } finally {
    await srv.close();
  }
});

test("cooldown, unknown player and expiry all answer over HTTP", async () => {
  const srv = await start({ cooldownMs: 1000, cost: 1, durationMs: 1000 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });
    const first = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    assert.equal(first.status, 200);

    const blocked = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "b") });
    assert.equal(blocked.status, 409);
    assert.equal(blocked.body.reason, "on_cooldown");

    const unknown = await post(srv.base, "/cast", { playerId: "nobody", candidates: [] });
    assert.equal(unknown.status, 404);
    assert.equal(unknown.body.reason, "unknown_player");

    const early = await post(srv.base, "/expire", { castId: first.body.event.castId });
    assert.equal(early.status, 404, "not expired yet");

    srv.advance(1000);
    const done = await post(srv.base, "/expire", { castId: first.body.event.castId });
    assert.equal(done.status, 200);
    assert.deepEqual(done.body.revertIds, ["a0"]);
  } finally {
    await srv.close();
  }
});

test("state exposes the mode cursor per player", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });
    await post(srv.base, "/players", { id: "p2", ownsCapri: true, capriSummoned: true, balance: 5 });
    await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    const res = await fetch(`${srv.base}/state`);
    const state = await res.json();
    assert.equal(res.status, 200);
    assert.equal(state.modeNext.p1, "blink", "p1 has consumed its turn");
    assert.equal(state.modeNext.p2, undefined, "p2 has not cast yet");
    assert.equal(state.mode, "alternate", "the default is alternating");
  } finally {
    await srv.close();
  }
});

test("a mode can be pinned over HTTP without restarting the server", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });

    const blink = await post(srv.base, "/mode", { mode: "blink" });
    assert.equal(blink.status, 200);
    assert.equal(blink.body.mode, "blink");
    const a = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    const b = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "b") });
    assert.equal(a.body.event.mode, "blink", "the pin overrides the first blackout");
    assert.equal(b.body.event.mode, "blink", "a pinned mode holds across casts");

    const blackout = await post(srv.base, "/mode", { mode: "blackout" });
    assert.equal(blackout.body.mode, "blackout");
    const c = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "c") });
    assert.equal(c.body.event.mode, "blackout", "the pin can be switched in place");

    const auto = await post(srv.base, "/mode", { mode: "alternate" });
    assert.equal(auto.body.mode, "alternate", "alternating comes back without a restart");
    const state = await (await fetch(`${srv.base}/state`)).json();
    assert.equal(state.mode, "alternate");
  } finally {
    await srv.close();
  }
});

test("an unknown mode is refused and changes nothing", async () => {
  const srv = await start({});
  try {
    const bad = await post(srv.base, "/mode", { mode: "strobe" });
    assert.equal(bad.status, 400);
    assert.match(bad.body.error, /blink, blackout or alternate/);
    const empty = await post(srv.base, "/mode", {});
    assert.equal(empty.status, 400, "a missing mode is refused too");
    const state = await (await fetch(`${srv.base}/state`)).json();
    assert.equal(state.mode, "alternate", "the mode is unchanged");
  } finally {
    await srv.close();
  }
});
