// Mass Override server-side logic: gate, per-player cooldown and cost,
// target claims, the per-cast target cap, and revert timers.
// Pure logic, no engine calls. The engine layer calls into this.

const DEFAULTS = {
  reach: 25, // one probe's radius; probes chain, so coverage is not this number
  probeBudget: 64, // probes per cast, mirrors MassOverrideProbe.MaxProbes()
  targetCap: 1000,
  // The 30 s effect, its revert and a margin; mirrors CapriMassOverride.Cooldown() (40 s).
  // Still a placeholder until the real value is decided (it was 120 s).
  cooldownMs: 40_000,
  cost: 25, // matches CapriMassOverride.ChargeCost() in the game scripts (RAM pool)
  durationMs: 30_000,
  // "alternate" (default) hands out one mode per cast, starting with blackout, the
  // same policy as MassOverridePrefs.Mode() in the game scripts. "blink" or
  // "blackout" pins that mode, the same as CapriMassOverride.Pin().
  mode: "alternate",
};

const REASONS = {
  OK: "ok",
  NOT_OWNER: "not_owner",
  NOT_SUMMONED: "not_summoned",
  ON_COOLDOWN: "on_cooldown",
  CANNOT_PAY: "cannot_pay",
};

// A world position a game sent: three finite numbers well inside Night City's map.
function isPoint(p) {
  return ["x", "y", "z"].every((k) => typeof p[k] === "number" && Number.isFinite(p[k]) && Math.abs(p[k]) < 1e6);
}

function createMassOverride(options = {}) {
  const cfg = { ...DEFAULTS, ...options };
  const cooldownUntil = new Map(); // playerId -> ms timestamp
  const balances = new Map(); // playerId -> resource amount
  const claims = new Map(); // targetId -> { castId, expiresAt }
  const active = new Map(); // castId -> { casterId, targetIds, expiresAt }
  let nextMode = "blackout"; // the mode the next cast hands out, shared by every player
  let nextCastId = 1;
  let nextSeq = 1; // feed sequence, one per accepted cast
  // Broadcast log: every accepted cast in the order it ran, so a client that was not
  // the caster reads the mode the server handed out instead of guessing from its own
  // cursor. Bounded, because a long session only ever needs the newest few and
  // nothing else prunes this.
  const events = [];
  const feedLimit = 64;

  function setBalance(playerId, amount) {
    balances.set(playerId, amount);
  }

  // Mirrors MassOverridePrefs.Mode(): a pinned mode wins, otherwise the cursor hands
  // out one mode and flips it, so the broadcast names the same mode the game will
  // run (blackout, blink, blackout...). One cursor for the whole session: a cast by
  // any player advances it, so the server and every client stay on the same beat
  // instead of each player alternating privately.
  function pickMode() {
    if (cfg.mode === "blink" || cfg.mode === "blackout") return cfg.mode;
    const mode = nextMode;
    nextMode = mode === "blackout" ? "blink" : "blackout";
    return mode;
  }

  // Pin a mode ("blink" / "blackout") or resume alternating ("alternate"),
  // the counterpart of CapriMassOverride.Pin() and Auto().
  function setMode(mode) {
    cfg.mode = mode === "blink" || mode === "blackout" ? mode : "alternate";
  }

  // Gate: owner, summoned, cooldown, cost. Checked in that order.
  function check(player, now) {
    if (!player.ownsCapri) return REASONS.NOT_OWNER;
    if (!player.capriSummoned) return REASONS.NOT_SUMMONED;
    if (now < (cooldownUntil.get(player.id) ?? 0)) return REASONS.ON_COOLDOWN;
    if ((balances.get(player.id) ?? 0) < cfg.cost) return REASONS.CANNOT_PAY;
    return REASONS.OK;
  }

  // Sweep result is a list of { id, type }. Claimed targets are skipped,
  // and the list is capped per cast.
  function selectTargets(candidates, castId, now) {
    const picked = [];
    for (const target of candidates) {
      if (picked.length >= cfg.targetCap) break;
      const claim = claims.get(target.id);
      if (claim && claim.expiresAt > now) continue;
      picked.push(target);
    }
    return picked;
  }

  // Attempt a cast. On success returns the event to broadcast and the
  // revert timer deadline. On failure returns the reason only.
  //
  // `origin` (from game builds that send it) is what every other client needs to run the
  // same street: where the caster stood ({x, y, z}, world metres), the mode the caster's own
  // game is running (so nobody runs the other one) and the caster's token for this cast (so
  // the caster's own game skips it when the feed hands it back).
  function cast(player, candidates, now, origin = null) {
    const reason = check(player, now);
    if (reason !== REASONS.OK) return { ok: false, reason };

    const castId = nextCastId++;
    const targets = selectTargets(candidates, castId, now);
    const expiresAt = now + cfg.durationMs;

    balances.set(player.id, balances.get(player.id) - cfg.cost);
    cooldownUntil.set(player.id, now + cfg.cooldownMs);
    for (const t of targets) claims.set(t.id, { castId, expiresAt });
    active.set(castId, {
      casterId: player.id,
      targetIds: targets.map((t) => t.id),
      expiresAt,
    });

    // The areas the cast actually reached, so a client can tell an Arroyo flood
    // from a Badlands one without re-deriving them from coordinates.
    const areas = [...new Set(targets.map((t) => t.area).filter(Boolean))];
    // Picked once, before the event is built: the feed must name the same mode this
    // cast ran, and calling pickMode() twice would hand the next cast the other one.
    // A game that says which mode it is running is taken at its word: that is what the
    // caster's street shows, so it is what every other client must show.
    const told = origin && (origin.mode === "blink" || origin.mode === "blackout") ? origin.mode : null;
    const mode = told ?? pickMode();
    const at = origin && isPoint(origin) ? { x: origin.x, y: origin.y, z: origin.z } : null;
    const token = origin && typeof origin.token === "string" ? origin.token : "";

    const event = { castId, casterId: player.id, targets, areas, mode, expiresAt, at, token };
    events.push({ seq: nextSeq++, castId, casterId: player.id, mode, areas, expiresAt, castAt: now, at, token });
    if (events.length > feedLimit) events.shift();

    return { ok: true, event };
  }

  // The casts every client runs: those after `since` that are still on (a cast whose effect
  // has ended is nothing to run), each with where it was cast and how long it has left.
  // `next` is the newest seq issued, the cursor the client keeps.
  function castsSince(since, now) {
    const parsed = Number(since);
    const after = Number.isFinite(parsed) ? parsed : 0;
    const active = events
      .filter((e) => e.seq > after && e.expiresAt > now)
      .map((e) => ({ ...e, ageMs: Math.max(0, now - e.castAt), remainingMs: Math.max(0, e.expiresAt - now) }));
    return { next: nextSeq - 1, events: active };
  }

  // Broadcast feed: the casts a client has not applied yet, oldest first, so a poller
  // that missed several still runs them in the order they happened rather than only
  // the newest. `since` is the seq the client last applied; anything unparseable
  // starts from the beginning of the retained log. `next` is the newest seq the
  // server has issued, so a caught-up poller can hold its cursor without skipping a
  // cast that lands between its request and the reply.
  function feedSince(since) {
    const parsed = Number(since);
    const after = Number.isFinite(parsed) ? parsed : 0;
    return { events: events.filter((e) => e.seq > after), next: nextSeq - 1 };
  }

  // Called by the server timer when a cast's duration has passed.
  // Returns the target IDs to revert, and releases their claims.
  function expire(castId, now) {
    const cast = active.get(castId);
    if (!cast || now < cast.expiresAt) return null;
    for (const id of cast.targetIds) {
      const claim = claims.get(id);
      if (claim && claim.castId === castId) claims.delete(id);
    }
    active.delete(castId);
    return { castId, revertIds: cast.targetIds };
  }

  // The last cast's own counts, as the client measured them. Kept so /state shows what
  // a cast actually applied instead of only what the gate accepted.
  let report = null;
  function setReport(value) {
    report = value;
  }

  return {
    cfg,
    REASONS,
    setBalance,
    setMode,
    setReport,
    check,
    cast,
    feedSince,
    castsSince,
    expire,
    // A getter, not a copied field: the cursor is a primitive that changes on every
    // cast, so a plain property would keep reporting the value it had at creation.
    _state: {
      cooldownUntil,
      balances,
      claims,
      active,
      get report() {
        return report;
      },
      get nextMode() {
        return nextMode;
      },
      events,
    },
  };
}

module.exports = { createMassOverride, REASONS, DEFAULTS, isPoint };
