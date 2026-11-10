const test = require("node:test");
const assert = require("node:assert/strict");
const { createEngineLayer } = require("./engine-adapter");

function mockAdapter(targets) {
  const calls = [];
  const events = [];
  return {
    calls,
    events,
    sweep: () => targets,
    setHostile: (id, on) => calls.push(["hostile", id, on]),
    setLights: (id, on) => calls.push(["lights", id, on]),
    setScreen: (id, on) => calls.push(["screen", id, on]),
    broadcast: (e) => events.push(e),
  };
}

function setup(targets, extra = {}) {
  let clock = 0;
  const timers = [];
  const adapter = mockAdapter(targets);
  const layer = createEngineLayer(adapter, {
    now: () => clock,
    schedule: (fn, ms) => {
      timers.push({ fn, at: clock + ms });
      return timers.length - 1;
    },
    unschedule: () => {},
    ...extra,
  });
  const owner = { id: "p1", ownsCapri: true, capriSummoned: true };
  layer.setBalance("p1", 25);
  return {
    adapter,
    layer,
    owner,
    advance: (ms) => {
      clock += ms;
      for (const t of timers.splice(0)) if (t.at <= clock) t.fn();
    },
  };
}

test("owner cast applies hostility and effects, then reverts on timer", () => {
  const targets = [
    { id: "npc1", type: "npc" },
    { id: "light1", type: "light" },
    { id: "tv1", type: "screen" },
  ];
  const { adapter, layer, owner, advance } = setup(targets);
  const res = layer.request(owner);
  assert.equal(res.ok, true);
  assert.equal(res.targets, 3);
  assert.ok(adapter.calls.some((c) => c[0] === "hostile" && c[1] === "npc1" && c[2] === true));
  assert.ok(adapter.calls.some((c) => c[0] === "lights" && c[1] === "light1" && c[2] === true));
  assert.ok(adapter.calls.some((c) => c[0] === "screen" && c[1] === "tv1" && c[2] === true));
  assert.equal(adapter.events[0].kind, "mass_override_start");

  advance(30_000);
  assert.ok(adapter.calls.some((c) => c[0] === "hostile" && c[1] === "npc1" && c[2] === false));
  assert.ok(adapter.calls.some((c) => c[0] === "lights" && c[1] === "light1" && c[2] === false));
  assert.ok(adapter.calls.some((c) => c[0] === "screen" && c[1] === "tv1" && c[2] === false));
  assert.equal(adapter.events.at(-1).kind, "mass_override_end");
});

test("non-owner request does nothing and sweeps nothing", () => {
  const { adapter, layer } = setup([{ id: "npc1", type: "npc" }]);
  const res = layer.request({ id: "p2", ownsCapri: false, capriSummoned: true });
  assert.deepEqual(res, { ok: false, reason: "not_owner" });
  assert.equal(adapter.calls.length, 0);
});

test("repeat cast during cooldown is rejected without effects", () => {
  const { adapter, layer, owner } = setup([{ id: "npc1", type: "npc" }]);
  layer.request(owner);
  const before = adapter.calls.length;
  const res = layer.request(owner);
  assert.equal(res.reason, "on_cooldown");
  assert.equal(adapter.calls.length, before);
});

test("claimed targets are released after revert and can be cast again", () => {
  const targets = [{ id: "npc1", type: "npc" }];
  const { layer, owner, advance } = setup(targets, { cooldownMs: 0 });
  layer.setBalance("p1", 75);
  layer.request(owner);
  const overlap = layer.request(owner);
  assert.equal(overlap.targets, 0, "claimed target is skipped during the cast");
  advance(30_000);
  const again = layer.request(owner);
  assert.equal(again.targets, 1, "target is free after the cast ends");
});

test("finish is idempotent", () => {
  const { layer, owner, adapter } = setup([{ id: "npc1", type: "npc" }]);
  const { castId } = layer.request(owner);
  layer.finish(castId);
  const ends = adapter.events.filter((e) => e.kind === "mass_override_end").length;
  layer.finish(castId);
  assert.equal(adapter.events.filter((e) => e.kind === "mass_override_end").length, ends);
});
