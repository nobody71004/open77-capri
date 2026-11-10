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

    // How long before the next cast may be paid for. The gate keeps the same clock
    // per player (mass-override/gate.js, 120_000 ms); without it here the game would
    // let V cast as fast as RAM allows while the server refused the same casts.
    public static func Cooldown() -> Float { return 120.0; }

    // What a cast costs out of the RAM pool. Capri's own hacks are free when she is set
    // not to use RAM and scale with ramScale (Capri.Actions.reds: Pay), so a cast costs
    // what hers cost instead of a number that ignores the setting. 0.0 = free.
    public static func Cost() -> Float {
        let settings = CapriStorage.Get().settings;
        if !settings.useRam { return 0.0; }
        return CapriMassOverride.ChargeCost() * settings.ramScale;
    }

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
    //
    // A mode the server broadcast for this cast wins over both the pin and the local
    // cursor (see ReceiveServerMode), so every client in a session runs the same
    // beat. With no broadcast the local sequence decides.
    public static func Mode(game: GameInstance) -> Int32 {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) { return prefs.Mode(); }
        return CapriMassOverride.ModeFromClock(game);
    }

    // Fallback when no service is registered to hold the cursor: whole seconds of sim
    // time decide, so an even second is blackout (the same first turn the cursor
    // takes) and an odd one is blink. Both modes stay reachable with nothing
    // registered and nothing to edit; two casts inside the same second repeat the
    // mode, so waiting a second flips it. Uses division and subtraction rather than
    // a modulo, which needs nothing beyond Int32 arithmetic.
    public static func ModeFromClock(game: GameInstance) -> Int32 {
        let now: Float = EngineTime.ToFloat(GameInstance.GetSimTime(game));
        let seconds: Int32 = Cast<Int32>(now);
        let half: Int32 = seconds / 2;
        if seconds - half * 2 == 0 {
            return MassOverrideMode.Blackout();
        }
        return MassOverrideMode.Blink();
    }

    // The one call the multiplayer layer makes when a cast arrives: hand over the mode
    // the server broadcast and it is consumed by the next cast. Kept as a static on
    // this class so the receive path never has to know about MassOverridePrefs.
    public static func ReceiveServerMode(mode: Int32) -> Void {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) { prefs.ReceiveServerMode(mode); }
    }

    // Where the last cast's mode came from, for the log line: "server" when a
    // broadcast supplied it, "local" when the pin, the cursor or the clock did.
    public static func ModeSource() -> String {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) && prefs.LastFromServer() { return "server"; }
        return "local";
    }

    // The pin in force, for the cast log line: "none" when casts alternate, otherwise
    // the mode Pin() fixed. Read separately from Mode(), which a server broadcast can
    // override for one cast.
    public static func PinLabel() -> String {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) { return prefs.PinnedMode(); }
        return "none";
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

    // Live control, the counterpart of the dev server's POST /mode: pin blink or
    // blackout for every following cast, or "auto" (also "alternate") to go back to
    // one mode per cast. Capri's action switch calls this with what V asked for, so a
    // session can be switched and switched back with no restart and no keybind.
    // Returns the mode in force ("blink", "blackout", "auto"), or "" when the word is
    // not a mode: nothing changes and the caller says nothing.
    public static func SetModeFromAction(target: String) -> String {
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if !IsDefined(prefs) {
            return "";
        }
        let word: String = StrLower(target);
        if Equals(word, "blink") {
            prefs.Pin(MassOverrideMode.Blink());
            return "blink";
        }
        if Equals(word, "blackout") || Equals(word, "black") {
            prefs.Pin(MassOverrideMode.Blackout());
            return "blackout";
        }
        if Equals(word, "auto") || Equals(word, "alternate") || Equals(word, "both") {
            prefs.Auto();
            return "auto";
        }
        return "";
    }

    // Run from CapriActions.Run. Returns "" when it worked, else why not (for the LLM and log).
    public static func Run(player: ref<PlayerPuppet>, system: ref<CapriSystem>) -> String {
        return CapriMassOverride.RunWith(player, system, CapriMassOverride.Mode(player.GetGame()));
    }

    public static func RunWith(player: ref<PlayerPuppet>, system: ref<CapriSystem>, mode: Int32) -> String {
        if !IsDefined(player) || !IsDefined(system) {
            return "not ready";
        }
        let cost: Float = CapriMassOverride.Cost();
        if cost > 0.0 && CapriActions.Ram(player) < cost {
            return "not enough battery charge for Mass Override";
        }
        let game: GameInstance = player.GetGame();
        let started: Float = EngineTime.ToFloat(GameInstance.GetSimTime(game));
        // The recharge is part of the cast, not a courtesy: a session can pay RAM for
        // one cast per cooldown, the same as the gate charges.
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) && prefs.Casts() > 0 {
            let waited: Float = started - prefs.LastCastAt();
            if waited < CapriMassOverride.Cooldown() {
                let left: Int32 = RoundF(CapriMassOverride.Cooldown() - waited);
                return "Mass Override is still recharging: " + ToString(left) + "s";
            }
        }
        let stats: ref<MassOverrideStats> = new MassOverrideStats();
        // Probes chain outward from V, so this reaches past 40 m and around corners.
        let targets = MassOverrideProbe.Collect(player, CapriMassOverride.Cap(), stats);
        if ArraySize(targets) == 0 {
            return "nothing to change around V";
        }
        // The same call Capri's own hacks make (Capri.Actions.reds: Spend), so the
        // charge goes through the game's stat pool rather than a number kept here.
        // The read is taken first: the pool change is a request, so a value read back
        // in this frame would still be the pre-charge one.
        let ramBefore: Float = CapriActions.Ram(player);
        if cost > 0.0 {
            GameInstance.GetStatPoolsSystem(game).RequestChangingStatPoolValue(
                Cast<StatsObjectID>(player.GetEntityID()), gamedataStatPoolType.Memory, -cost, player, false, false);
        }
        if IsDefined(prefs) { prefs.MarkCastAt(started); }
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
                + " modeSource=" + CapriMassOverride.ModeSource()
                + " pin=" + CapriMassOverride.PinLabel()
                + " cost=" + ToString(RoundF(cost))
                + " ram=" + ToString(ramBefore)
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
            // Once per session, not once per cast: a service that never registers is
            // still worth saying, but not 30 times a fight.
            if !MassOverrideDiag.AllPresent() && MassOverrideDiag.ShouldWarn(game) {
                FTLog("[MassOverride] service missing: " + services);
            }
        }
        return "";
    }
}
