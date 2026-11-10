const test = require("node:test");
const assert = require("node:assert/strict");
const { createMassOverride, REASONS } = require("./gate");

const owner = (id, extra = {}) => ({
  id,
  ownsCapri: true,
  capriSummoned: true,
  ...extra,
});
const targets = (n, prefix = "t") =>
  Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i}`, type: "light" }));

test("rejects non-owner, then unsummoned, in that order", () => {
  const mo = createMassOverride();
  mo.setBalance("a", 10);
  assert.equal(
    mo.cast({ id: "a", ownsCapri: false, capriSummoned: false }, [], 0).reason,
    REASONS.NOT_OWNER,
  );
  assert.equal(
    mo.cast({ id: "a", ownsCapri: true, capriSummoned: false }, [], 0).reason,
    REASONS.NOT_SUMMONED,
  );
});

test("cooldown and cost are per player", () => {
  const mo = createMassOverride({ cooldownMs: 1000, cost: 1 });
  mo.setBalance("a", 5);
  mo.setBalance("b", 5);
  assert.equal(mo.cast(owner("a"), targets(2, "a"), 0).ok, true);
  assert.equal(mo.cast(owner("a"), targets(2, "a2"), 500).reason, REASONS.ON_COOLDOWN);
  // b is not blocked by a's cooldown.
  assert.equal(mo.cast(owner("b"), targets(2, "b"), 500).ok, true);
  // a can cast again after its cooldown.
  assert.equal(mo.cast(owner("a"), targets(2, "a3"), 1000).ok, true);
});

test("cannot pay blocks the cast and charges nothing", () => {
  const mo = createMassOverride({ cost: 2 });
  mo.setBalance("a", 1);
  assert.equal(mo.cast(owner("a"), targets(1), 0).reason, REASONS.CANNOT_PAY);
  assert.equal(mo._state.balances.get("a"), 1);
  assert.equal(mo._state.cooldownUntil.has("a"), false);
});

test("a failed gate does not start a cooldown", () => {
  const mo = createMassOverride({ cost: 5 });
  mo.setBalance("a", 0);
  mo.cast(owner("a"), targets(1), 0);
  mo.setBalance("a", 5);
  assert.equal(mo.cast(owner("a"), targets(1), 0).ok, true);
});

test("caps targets per cast at 1000", () => {
  const mo = createMassOverride({ targetCap: 1000 });
  mo.setBalance("a", 25);
  const res = mo.cast(owner("a"), targets(1500), 0);
  assert.equal(res.ok, true);
  assert.equal(res.event.targets.length, 1000);
});

test("claimed targets are skipped by a second cast until expiry", () => {
  const mo = createMassOverride({ durationMs: 1000, cooldownMs: 0 });
  mo.setBalance("a", 50);
  mo.setBalance("b", 50);
  const shared = targets(3, "s");
  mo.cast(owner("a"), shared, 0);
  const second = mo.cast(owner("b"), shared, 500);
  assert.equal(second.event.targets.length, 0);
  // After the first cast's claims expire, b can take them.
  const third = mo.cast(owner("b"), shared, 1000);
  assert.equal(third.event.targets.length, 3);
});

test("expire releases claims and returns targets to revert", () => {
  const mo = createMassOverride({ durationMs: 1000, cooldownMs: 0 });
  mo.setBalance("a", 25);
  const res = mo.cast(owner("a"), targets(2), 0);
  assert.equal(mo.expire(res.event.castId, 999), null, "not before expiry");
  const done = mo.expire(res.event.castId, 1000);
  assert.deepEqual(done.revertIds, ["t0", "t1"]);
  assert.equal(mo._state.claims.size, 0);
});

test("blink is the default mode and blackout stays selectable", () => {
  const blink = createMassOverride({ cost: 0, cooldownMs: 0 });
  blink.setBalance("a", 1);
  assert.equal(blink.cast(owner("a"), targets(1, "x"), 0).event.mode, "blink");

  const blackout = createMassOverride({ cost: 0, cooldownMs: 0, mode: "blackout" });
  blackout.setBalance("a", 1);
  assert.equal(blackout.cast(owner("a"), targets(1, "y"), 0).event.mode, "blackout");
});

test("a cast reports the areas its targets are in", () => {
  const mo = createMassOverride({ cost: 0, cooldownMs: 0 });
  mo.setBalance("a", 1);
  const res = mo.cast(
    owner("a"),
    [
      { id: "l1", type: "light", area: "Watson:4:2" },
      { id: "l2", type: "light", area: "Watson:4:2" },
      { id: "b1", type: "billboard", area: "Watson:5:2" },
      { id: "n1", type: "npc" },
    ],
    0,
  );
  assert.equal(res.ok, true);
  assert.deepEqual(res.event.areas.sort(), ["Watson:4:2", "Watson:5:2"]);
  assert.equal(res.event.targets.length, 4, "targets without an area are still affected");
});
