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

test("state exposes the shared mode cursor", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });
    await post(srv.base, "/players", { id: "p2", ownsCapri: true, capriSummoned: true, balance: 5 });
    await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    const res = await fetch(`${srv.base}/state`);
    const state = await res.json();
    assert.equal(res.status, 200);
    assert.equal(state.nextMode, "blink", "the cast advanced the shared cursor");
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

test("the feed replays an accepted cast once and then reports none", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });
    const first = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    assert.equal(first.status, 200);

    const cold = await fetch(`${srv.base}/feed?since=0`);
    assert.equal(cold.headers.get("content-type"), "text/plain");
    assert.equal(await cold.text(), "1 blackout", "a client that has seen nothing gets the cast");

    const caughtUp = await fetch(`${srv.base}/feed?since=1`);
    assert.equal(await caughtUp.text(), "1 none", "its own cursor comes back so it never rewinds");
  } finally {
    await srv.close();
  }
});

test("the feed hands out the server's mode, not the client's guess", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 5 });
    await post(srv.base, "/players", { id: "p2", ownsCapri: true, capriSummoned: true, balance: 5 });
    await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    await post(srv.base, "/cast", { playerId: "p2", candidates: candidates(1, "b") });

    const seen = await (await fetch(`${srv.base}/feed?since=0`)).text();
    assert.equal(seen, "2 blink", "the newest unseen cast carries the second mode");

    const events = await (await fetch(`${srv.base}/events?since=0`)).json();
    assert.equal(events.next, 2);
    assert.equal(events.events.length, 2, "a poller that missed one still sees both");
    assert.deepEqual(events.events.map((e) => e.mode), ["blackout", "blink"]);
    assert.equal(events.events[0].casterId, "p1");
  } finally {
    await srv.close();
  }
});

test("a refused cast never reaches the feed", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: false, balance: 50 });
    const refused = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    assert.equal(refused.status, 409);

    assert.equal(await (await fetch(`${srv.base}/feed?since=0`)).text(), "0 none");
    const events = await (await fetch(`${srv.base}/events?since=0`)).json();
    assert.deepEqual(events.events, []);
  } finally {
    await srv.close();
  }
});

test("a refused cast over HTTP leaves the shared beat alone", async () => {
  const srv = await start({ cooldownMs: 0, cost: 0 });
  try {
    await post(srv.base, "/players", { id: "p1", ownsCapri: true, capriSummoned: true, balance: 50 });
    await post(srv.base, "/players", { id: "p2", ownsCapri: true, capriSummoned: false, balance: 50 });
    const first = await post(srv.base, "/cast", { playerId: "p1", candidates: candidates(1, "a") });
    assert.equal(first.status, 200);
    assert.equal(first.body.event.mode, "blackout");

    const refused = await post(srv.base, "/cast", { playerId: "p2", candidates: candidates(1, "b") });
    assert.equal(refused.status, 409);
    assert.equal(refused.body.reason, "not_summoned");

    const state = await (await fetch(`${srv.base}/state`)).json();
    assert.equal(state.nextMode, "blink", "the refusal did not consume the beat");
  } finally {
    await srv.close();
  }
});
