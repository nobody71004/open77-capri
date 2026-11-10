// Mass Override wiring: runs a cast through the gate, applies the effects
// through an engine adapter, and reverts them when the duration ends.
//
// The adapter is the only part that touches the game. Its methods map to calls
// read from the game's own shipped sources (docs/MASS_OVERRIDE.md):
//   sweep(player)       -> candidate targets within the radius
//   setHostile(id, on)  -> AttitudeAgent.SetAttitudeTowards(AIA_Hostile) / revert
//   setBlink(id, on)    -> IComponent.Toggle on that entity's world widget
//                          components (billboards, TVs, LCD screens) and its
//                          lights, including vehicle lights
//   broadcast(event)    -> one event to every client
//
// A target's type decides the effect, and only two effects exist:
//   "npc"    people turn hostile
//   "device" screens, billboards, TVs, lights and vehicles go dark
// Anything that is not a puppet is blinked, because hostility is only defined
// for a puppet. `on` is true when the override starts and false when it reverts;
// the engine layer maps it onto the component toggle (dark on start, back on
// revert).

const { createMassOverride, REASONS } = require("./gate");

function createEngineLayer(adapter, options = {}) {
  const gate = createMassOverride(options);
  const timers = new Map(); // castId -> timer handle
  const castTargets = new Map(); // castId -> targets applied
  const now = options.now ?? (() => Date.now());
  const schedule = options.schedule ?? setTimeout;
  const unschedule = options.unschedule ?? clearTimeout;

  function applyTarget(t, on) {
    if (t.type === "npc") adapter.setHostile(t.id, on);
    else adapter.setBlink(t.id, on);
  }

  // Request from a client. The server does the sweep; the client sends only
  // the request. Returns the gate result.
  function request(player) {
    const t = now();
    const reason = gate.check(player, t);
    if (reason !== REASONS.OK) return { ok: false, reason };

    const candidates = adapter.sweep(player);
    const result = gate.cast(player, candidates, t);
    if (!result.ok) return result;

    const { event } = result;
    castTargets.set(event.castId, event.targets);
    for (const target of event.targets) applyTarget(target, true);
    adapter.broadcast({ kind: "mass_override_start", ...event });

    timers.set(
      event.castId,
      schedule(() => finish(event.castId), gate.cfg.durationMs),
    );
    return { ok: true, castId: event.castId, targets: event.targets.length };
  }

  // Ends a cast: reverts hostility and effects, releases claims, and
  // broadcasts the end. Safe to call once per cast; later calls return null.
  function finish(castId) {
    const done = gate.expire(castId, Number.POSITIVE_INFINITY);
    timers.delete(castId);
    if (!done) return null;
    const targets = castTargets.get(castId) ?? [];
    castTargets.delete(castId);
    for (const target of targets) applyTarget(target, false);
    adapter.broadcast({ kind: "mass_override_end", castId });
    return done;
  }

  function setBalance(playerId, amount) {
    gate.setBalance(playerId, amount);
  }

  function stop() {
    for (const handle of timers.values()) unschedule(handle);
    timers.clear();
  }

  return { request, finish, setBalance, stop, gate };
}

module.exports = { createEngineLayer };
