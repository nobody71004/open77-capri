// Capri: Mass Override - one action that changes many things around V at once.
// Only Capri runs it (her own action code, no item or keybind).
// Sandevistan is reference only; there is no time dilation here.
// The multi-probe sweep, the area cells, the modes and the effects live in
// Open77MassOverride.reds.
//
// This file references nothing outside the stock Capri build on purpose. An
// earlier version called CapriSystem.MassOverrideShown() and read
// CapriStorage.massOverrideLastAt, which meant it only compiled once matching
// edits in Capri.System.reds and Capri.Storage.reds had been synced too; twice
// they had not, and the whole script set failed to compile. `settings` and
// `settings.unleashed` are stock fields, used by stock Capri everywhere.
module Capri

public class CapriMassOverride extends IScriptable {

    // Battery charge per cast, taken from the RAM pool (placeholder value).
    public static func ChargeCost() -> Float { return 25.0; }

    // Targets one cast may change. The probe budget in MassOverrideProbe bounds
    // how far the fill walks; this bounds how much it may change.
    public static func Cap() -> Int32 { return 1000; }

    // How long people stay hostile and the block stays lit or dark before it reverts.
    public static func Duration() -> Float { return 30.0; }

    // 1 logs one measurement line per cast. Set it false to silence the log.
    public static func Instrumented() -> Bool { return true; }

    // The mode for the next cast, taken from Mass Override's own state
    // (MassOverridePrefs): the first cast is blackout and every cast after it flips
    // between blackout and blink, so both are reachable per cast with nothing to
    // press and nothing to edit; Pin() fixes one and Auto() resumes alternating. This
    // is deliberately NOT read from Capri's settings --
    // `settings.unleashed` is her quickhack tier (Capri.Storage.reds: "her quickhacks
    // at their strongest tier"), and mapping a visual mode onto it made blackout
    // unreachable for anyone who had that turned off.
    public static func Mode() -> Int32 {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) { return prefs.Mode(); }
        // Same as the pinned default: if the service is missing, a cast still does
        // what it ships as, rather than silently falling back to blink.
        return MassOverrideMode.Blackout();
    }

    // Fix a mode for every following cast, or pass -1 to alternate again. Both are
    // one call, so Capri's own action code can choose per request when Mass Override
    // is wired into her action table.
    public static func Pin(mode: Int32) -> Void {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) { prefs.Pin(mode); }
    }

    public static func Auto() -> Void {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) { prefs.Auto(); }
    }

    // Run from CapriActions.Run. Returns "" when it worked, else why not (for the LLM and log).
    public static func Run(player: ref<PlayerPuppet>, system: ref<CapriSystem>) -> String {
        return CapriMassOverride.RunWith(player, system, CapriMassOverride.Mode());
    }

    public static func RunWith(player: ref<PlayerPuppet>, system: ref<CapriSystem>, mode: Int32) -> String {
        if !IsDefined(player) || !IsDefined(system) {
            return "not ready";
        }
        if CapriActions.Ram(player) < CapriMassOverride.ChargeCost() {
            return "not enough battery charge for Mass Override";
        }
        let game: GameInstance = player.GetGame();
        let started: Float = EngineTime.ToFloat(GameInstance.GetSimTime(game));
        let stats: ref<MassOverrideStats> = new MassOverrideStats();
        // Probes chain outward from V, so this reaches past 40 m and around corners.
        let targets = MassOverrideProbe.Collect(player, CapriMassOverride.Cap(), stats);
        if ArraySize(targets) == 0 {
            return "nothing to change around V";
        }
        GameInstance.GetStatPoolsSystem(game).RequestChangingStatPoolValue(
            Cast<StatsObjectID>(player.GetEntityID()), gamedataStatPoolType.Memory, -CapriMassOverride.ChargeCost(), player, false, false);
        let blackout: Bool = mode == MassOverrideMode.Blackout();
        let i: Int32 = 0;
        while i < ArraySize(targets) {
            let object: ref<GameObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as GameObject;
            if targets[i].kind == 0 {
                // People turn on V in both modes.
                MassOverrideEffects.SetHostile(object as NPCPuppet, player, true);
            } else {
                // Blink leaves the block lit for the first pulse; blackout drops it now.
                stats.changed += MassOverrideEffects.BlinkReported(object, !blackout, stats);
            }
            i += 1;
        }
        let cycles: Int32 = RoundF(CapriMassOverride.Duration() / MassOverridePulse.Interval()) + 1;
        if blackout {
            // Not a single toggle: a device's own controller switches its screen and
            // lights back on within a frame or two. The blink survived because it
            // re-asserts twice a second; the one-shot blackout did not, and read as
            // nothing happening. Hold it dark for the duration instead.
            let hold: ref<MassOverrideHold> = new MassOverrideHold();
            hold.game = game;
            hold.targets = targets;
            hold.cyclesLeft = cycles;
            GameInstance.GetDelaySystem(game).DelayCallback(hold, MassOverrideHold.Interval(), false);
        } else {
            let pulse: ref<MassOverridePulse> = new MassOverridePulse();
            pulse.game = game;
            pulse.targets = targets;
            pulse.cyclesLeft = cycles;
            pulse.lit = false;
            GameInstance.GetDelaySystem(game).DelayCallback(pulse, MassOverridePulse.Interval(), false);
        }
        // Revert on a delay, not on Capri: dismissing her does not end it early.
        let revert: ref<MassOverrideRevert> = new MassOverrideRevert();
        revert.game = game;
        revert.player = player;
        revert.targets = targets;
        GameInstance.GetDelaySystem(game).DelayCallback(revert, CapriMassOverride.Duration(), false);
        stats.seconds = EngineTime.ToFloat(GameInstance.GetSimTime(game)) - started;
        if CapriMassOverride.Instrumented() {
            // One grep-able line per cast. At 100, 500 and 1000 targets the counts
            // are the measurement; `secs` is reported too, but a fill happens in a
            // single frame, so it can honestly read 0.000.
            let services: String = MassOverrideDiag.Describe();
            FTLog("[MassOverride] mode=" + (blackout ? "blackout" : "blink")
                + " area=" + MassOverrideArea.Name(game, player.GetWorldPosition())
                + " cache=" + (stats.cacheHit ? "hit" : "miss")
                + " blocks=" + ToString(stats.blocks)
                + " probes=" + ToString(stats.probes)
                + " parts=" + ToString(stats.parts)
                + " people=" + ToString(stats.people)
                + " devices=" + ToString(stats.devices)
                + " screens=" + ToString(stats.screens)
                + " lights=" + ToString(stats.lights)
                + " lightStates=" + ToString(stats.lightStates)
                + " lightFallbacks=" + ToString(stats.lightFallbacks)
                + " lightEvents=" + ToString(stats.lightEvents)
                + " vehicles=" + ToString(stats.vehicles)
                + " changed=" + ToString(stats.changed)
                + " targets=" + ToString(ArraySize(targets))
                + " cap=" + ToString(CapriMassOverride.Cap())
                + " secs=" + ToString(stats.seconds)
                + " services=" + services);
            // Said out loud, not inferred: a service that did not register explains a
            // mode that never alternates or a cache that never hits.
            if !MassOverrideDiag.AllPresent() {
                FTLog("[MassOverride] service missing: " + services);
            }
        }
        return "";
    }
}
