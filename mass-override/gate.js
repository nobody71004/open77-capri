// Mass Override server-side logic: gate, per-player cooldown and cost,
// target claims, the per-cast target cap, and revert timers.
// Pure logic, no engine calls. The engine layer calls into this.

const DEFAULTS = {
  reach: 25, // one probe's radius; probes chain, so coverage is not this number
  probeBudget: 64, // probes per cast, mirrors MassOverrideProbe.MaxProbes()
  targetCap: 1000,
  cooldownMs: 120_000, // placeholder until the cooldown is decided
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

function createMassOverride(options = {}) {
  const cfg = { ...DEFAULTS, ...options };
  const cooldownUntil = new Map(); // playerId -> ms timestamp
  const balances = new Map(); // playerId -> resource amount
  const claims = new Map(); // targetId -> { castId, expiresAt }
  const active = new Map(); // castId -> { casterId, targetIds, expiresAt }
  const modeNext = new Map(); // playerId -> the mode the next cast hands out
  let nextCastId = 1;

  function setBalance(playerId, amount) {
    balances.set(playerId, amount);
  }

  // Mirrors MassOverridePrefs.Mode(): a pinned mode wins, otherwise the cursor hands
  // out one mode and flips it, so the broadcast names the same mode the game will
  // run (blackout, blink, blackout...). Per player, because in the game the
  // preference is each client's own.
  function pickMode(playerId) {
    if (cfg.mode === "blink" || cfg.mode === "blackout") return cfg.mode;
    const mode = modeNext.get(playerId) ?? "blackout";
    modeNext.set(playerId, mode === "blackout" ? "blink" : "blackout");
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
  function cast(player, candidates, now) {
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

    return {
      ok: true,
      event: {
        castId,
        casterId: player.id,
        targets,
        areas,
        mode: pickMode(player.id),
        expiresAt,
      },
    };
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

  return {
    cfg,
    REASONS,
    setBalance,
    setMode,
    check,
    cast,
    expire,
    _state: { cooldownUntil, balances, claims, active, modeNext },
  };
}

module.exports = { createMassOverride, REASONS, DEFAULTS };
