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

    // Blink is the default: the block strobes, which reads as an overload rather
    // than a power cut. Capri's own `unleashed` setting is the switch that already
    // exists in her build, so blackout is selectable today without a new storage
    // field and without editing another Capri file. RunWith is the explicit door
    // for a future per-action choice.
    public static func Mode() -> Int32 {
        let storage: ref<CapriStorage> = CapriStorage.Get();
        if !IsDefined(storage) {
            return MassOverrideMode.Blink();
        }
        let settings: ref<CapriSettingsDTO> = storage.settings;
        if !IsDefined(settings) {
            return MassOverrideMode.Blink();
        }
        return settings.unleashed ? MassOverrideMode.Blackout() : MassOverrideMode.Blink();
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
                stats.changed += MassOverrideEffects.Blink(object, !blackout);
            }
            i += 1;
        }
        if !blackout {
            let pulse: ref<MassOverridePulse> = new MassOverridePulse();
            pulse.game = game;
            pulse.targets = targets;
            pulse.cyclesLeft = RoundF(CapriMassOverride.Duration() / MassOverridePulse.Interval()) + 1;
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
            FTLog("[MassOverride] mode=" + (blackout ? "blackout" : "blink")
                + " area=" + MassOverrideArea.Name(game, player.GetWorldPosition())
                + " cache=" + (stats.cacheHit ? "hit" : "miss")
                + " blocks=" + ToString(stats.blocks)
                + " probes=" + ToString(stats.probes)
                + " parts=" + ToString(stats.parts)
                + " people=" + ToString(stats.people)
                + " devices=" + ToString(stats.devices)
                + " changed=" + ToString(stats.changed)
                + " targets=" + ToString(ArraySize(targets))
                + " cap=" + ToString(CapriMassOverride.Cap())
                + " secs=" + ToString(stats.seconds));
        }
        return "";
    }
}
