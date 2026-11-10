// Capri: Mass Override - one action that changes many things around V at once.
// Only Capri runs it (her own action code, no item or keybind).
// Sandevistan is reference only; there is no time dilation here.
// The multi-probe sweep, the area cells and the effects live in
// Open77MassOverride.reds.
//
// This file references nothing outside the stock Capri build on purpose. An
// earlier version called CapriSystem.MassOverrideShown() and read
// CapriStorage.massOverrideLastAt, which meant it only compiled once matching
// edits in Capri.System.reds and Capri.Storage.reds had been synced too; twice
// they had not, and the whole script set failed to compile. Ownership, "Capri is
// summoned", cooldown and cost are decided by the server gate
// (mass-override/gate.js), which is where the request is admitted, so nothing
// here needs a storage field of its own.
module Capri

public class CapriMassOverride extends IScriptable {

    // Battery charge per cast, taken from the RAM pool (placeholder value).
    public static func ChargeCost() -> Float { return 25.0; }

    // Targets one cast may change. The probe budget in MassOverrideProbe bounds
    // how far the fill walks; this bounds how much it may change.
    public static func Cap() -> Int32 { return 1000; }

    // How long people stay hostile and the block stays dark before it reverts.
    public static func Duration() -> Float { return 30.0; }

    // Run from CapriActions.Run. Returns "" when it worked, else why not (for the LLM and log).
    public static func Run(player: ref<PlayerPuppet>, system: ref<CapriSystem>) -> String {
        if !IsDefined(player) || !IsDefined(system) {
            return "not ready";
        }
        if CapriActions.Ram(player) < CapriMassOverride.ChargeCost() {
            return "not enough battery charge for Mass Override";
        }
        // Probes chain outward from V, so this reaches past 40 m and around corners.
        let targets = MassOverrideProbe.Collect(player, CapriMassOverride.Cap());
        if ArraySize(targets) == 0 {
            return "nothing to change around V";
        }
        GameInstance.GetStatPoolsSystem(player.GetGame()).RequestChangingStatPoolValue(
            Cast<StatsObjectID>(player.GetEntityID()), gamedataStatPoolType.Memory, -CapriMassOverride.ChargeCost(), player, false, false);
        let i: Int32 = 0;
        while i < ArraySize(targets) {
            let object: ref<GameObject> = GameInstance.FindEntityByID(player.GetGame(), targets[i].entityId) as GameObject;
            if targets[i].kind == 0 {
                // People turn on V.
                MassOverrideEffects.SetHostile(object as NPCPuppet, player, true);
            } else {
                // Screens, billboards, lights and vehicle lights go dark.
                MassOverrideEffects.Blink(object, false);
            }
            i += 1;
        }
        // Revert on a delay, not on Capri: dismissing her does not end it early.
        let revert: ref<MassOverrideRevert> = new MassOverrideRevert();
        revert.game = player.GetGame();
        revert.player = player;
        revert.targets = targets;
        GameInstance.GetDelaySystem(player.GetGame()).DelayCallback(revert, CapriMassOverride.Duration(), false);
        return "";
    }
}
