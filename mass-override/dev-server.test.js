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

// ---------------------------------------------------------------------------------------------
// Every client runs every cast (2026-11-12): sessions, positions and GET /casts.

function startLogged(options = {}) {
  const lines = [];
  return start({ ...options, log: (l) => lines.push(l) }).then((srv) => ({ ...srv, lines }));
}

async function get(base, route) {
  const res = await fetch(`${base}${route}`);
  return { status: res.status, text: await res.text() };
}

test("a cast with a session needs no /players first, and keeps its own cooldown", async () => {
  const srv = await startLogged({ cooldownMs: 40_000, cost: 25, durationMs: 30_000 });
  try {
    const a = await post(srv.base, "/cast", { playerId: "(EntityID 1)", session: "s111", token: "s111-1", mode: "blink", x: 10.5, y: -20.25, z: 3, candidates: candidates(2, "a") });
    assert.equal(a.status, 200);
    assert.equal(a.body.event.mode, "blink", "the caster's own mode is the event's");
    assert.deepEqual(a.body.event.at, { x: 10.5, y: -20.25, z: 3 });
    // the same entity id from another PC is another player: its own session, its own cooldown
    const b = await post(srv.base, "/cast", { playerId: "(EntityID 1)", session: "s222", token: "s222-1", mode: "blackout", x: 0, y: 0, z: 0, candidates: [] });
    assert.equal(b.status, 200, "another PC is not held by the first one's cooldown");
    const again = await post(srv.base, "/cast", { playerId: "(EntityID 1)", session: "s111", token: "s111-2", mode: "blink", x: 1, y: 1, z: 1, candidates: [] });
    assert.equal(again.status, 409);
    assert.equal(again.body.reason, "on_cooldown");
    assert.ok(srv.lines.some((l) => l.startsWith("[cast] seq=1 by s111 mode=blink at 10.5,-20.3,3.0 token=s111-1")), srv.lines.join("\n"));
    assert.ok(srv.lines.some((l) => l.startsWith("[cast] refused for s111: on_cooldown")));
  } finally {
    await srv.close();
  }
});

test("GET /casts hands every client the casts still on, with where they were cast", async () => {
  const srv = await startLogged({ cooldownMs: 0, cost: 0, durationMs: 30_000 });
  try {
    let r = await get(srv.base, "/casts?since=0&session=s9");
    assert.equal(r.status, 200);
    assert.equal(r.text, "0", "nothing cast yet: only the cursor");
    await post(srv.base, "/cast", { playerId: "x", session: "s1", token: "s1-1", mode: "blackout", x: -1234.56, y: 789.01, z: 22.5, candidates: [] });
    srv.advance(5_000);
    r = await get(srv.base, "/casts?since=0&session=s9");
    const [next, line] = r.text.split("\n");
    assert.equal(next, "1");
    assert.equal(line, "1 blackout -123456 78901 2250 5000 25000 s1-1");
    // caught up: the cursor alone
    assert.equal((await get(srv.base, "/casts?since=1&session=s9")).text, "1");
    // a cast that has ended is not handed out any more
    srv.advance(26_000);
    assert.equal((await get(srv.base, "/casts?since=0&session=s9")).text, "1");
    assert.ok(srv.lines.some((l) => l.startsWith("[feed] new client s9 polling (1 polling)")), srv.lines.join("\n"));
  } finally {
    await srv.close();
  }
});

test("a cast from an older build (no session, no position) is still handed out, marked nopos", async () => {
  const srv = await startLogged({ cooldownMs: 0, cost: 0, durationMs: 30_000 });
  try {
    await post(srv.base, "/players", { id: "(EntityID 1)", ownsCapri: true, capriSummoned: true, balance: 100 });
    const old = await post(srv.base, "/cast", { playerId: "(EntityID 1)", candidates: candidates(1, "o") });
    assert.equal(old.status, 200);
    assert.equal(old.body.event.mode, "blackout", "an older build still gets the gate's own beat");
    const r = await get(srv.base, "/casts?since=0");
    assert.equal(r.text.split("\n")[1], "1 blackout 0 0 0 0 30000 nopos");
    // the old feed still answers the way builds up to 1.16.16 read it
    assert.equal((await get(srv.base, "/feed?since=0")).text, "1 blackout");
  } finally {
    await srv.close();
  }
});

test("a bad token or a position out of the map is not passed on", async () => {
  const srv = await startLogged({ cooldownMs: 0, cost: 0, durationMs: 30_000 });
  try {
    const r = await post(srv.base, "/cast", { session: "s5", token: "bad token!", mode: "sideways", x: 1e9, y: 0, z: 0, candidates: [] });
    assert.equal(r.status, 200);
    assert.equal(r.body.event.at, null);
    assert.equal(r.body.event.token, "");
    assert.ok(["blink", "blackout"].includes(r.body.event.mode));
    assert.equal((await get(srv.base, "/casts?since=0")).text.split("\n")[1].split(" ").slice(-1)[0], "nopos");
  } finally {
    await srv.close();
  }
});

test("/state names the clients polling and the recent casts", async () => {
  const srv = await startLogged({ cooldownMs: 0, cost: 0, durationMs: 30_000 });
  try {
    await get(srv.base, "/casts?since=0&session=sA");
    await get(srv.base, "/casts?since=0&session=sB");
    await post(srv.base, "/cast", { session: "sA", token: "sA-1", mode: "blink", x: 1, y: 2, z: 3, candidates: [] });
    const res = await fetch(`${srv.base}/state`);
    const s = await res.json();
    assert.equal(s.polling, 2);
    assert.deepEqual(Object.keys(s.pollers).sort(), ["sA", "sB"]);
    assert.equal(s.recent.length, 1);
    assert.deepEqual(s.recent[0].at, [1, 2, 3]);
    assert.equal(s.stats.casts, 1);
  } finally {
    await srv.close();
  }
});

test("the same cast sent again (its first try got no answer) is answered with the cast on, never run twice", async () => {
  const lines = [];
  const srv = await start({ log: (l) => lines.push(l) });
  try {
    const cast = { session: "s111111222222", token: "s111111222222-1", mode: "blink", x: -686.3, y: 1151.7, z: 28.6,
      candidates: candidates(4, "c") };
    const first = await post(srv.base, "/cast", cast);
    assert.equal(first.status, 200);
    srv.advance(3000);
    // the second try: same token -- inside the caster's recharge, still answered as the cast it is
    const again = await post(srv.base, "/cast", cast);
    assert.equal(again.status, 200);
    assert.equal(again.body.duplicate, true);
    assert.equal(again.body.event.castId, first.body.event.castId);
    assert.equal(again.body.event.mode, "blink");
    // handed out once
    const feed = await (await fetch(`${srv.base}/casts?since=0&session=s999`)).text();
    assert.equal(feed.trim().split("\n").length, 2, feed);
    const state = await (await fetch(`${srv.base}/state`)).json();
    assert.equal(state.stats.casts, 1);
    assert.equal(state.stats.again, 1);
    assert.equal(state.balances.s111111222222, 75, "charged once");
    assert.ok(lines.some((l) => /^\[cast\] again from s111111222222 token=s111111222222-1: seq=1 is on already/.test(l)), lines.join("\n"));
    // a NEW cast inside the recharge is still refused
    const next = await post(srv.base, "/cast", { ...cast, token: "s111111222222-2" });
    assert.equal(next.status, 409);
    assert.equal(next.body.reason, "on_cooldown");
    // another game's cast with the same token text is its own cast
    const other = await post(srv.base, "/cast", { ...cast, session: "s333333444444" });
    assert.equal(other.status, 200);
    assert.equal(other.body.duplicate, undefined);
  } finally {
    await srv.close();
  }
});

test("a request the gate cannot read is answered 400 and said in its log", async () => {
  const lines = [];
  const srv = await start({ log: (l) => lines.push(l) });
  try {
    const res = await fetch(`${srv.base}/cast`, { method: "POST", headers: { "content-type": "application/json" },
      body: '{"session":"s1","candidates":[{"id":"a\\q"}]}' });
    assert.equal(res.status, 400);
    assert.ok(lines.some((l) => /^\[http\] POST \/cast -> 400: /.test(l)), lines.join("\n"));
    const state = await (await fetch(`${srv.base}/state`)).json();
    assert.equal(state.stats.bad, 1);
  } finally {
    await srv.close();
  }
});
