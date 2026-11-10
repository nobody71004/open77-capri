// Capri: Mass Override - one action that changes many things around V at once.
// Only Capri runs it (her own action code, no item or keybind).
// Sandevistan is reference only; there is no time dilation here.
// Sweep and effects live in Open77MassOverride.reds.
module Capri

public class CapriMassOverride extends IScriptable {

    // Seconds before Capri can run it again for the same player.
    public static func Cooldown() -> Float { return 120.0; }

    // Battery charge per cast, taken from the RAM pool (placeholder value).
    public static func ChargeCost() -> Float { return 25.0; }

    // Sweep radius and target cap (matches the bridge in Open77MassOverride.reds).
    public static func Radius() -> Float { return 40.0; }
    public static func Cap() -> Int32 { return 1000; }

    // How long people stay hostile and the block stays dark before it reverts.
    public static func Duration() -> Float { return 30.0; }

    // Run from CapriActions.Run. Returns "" when it worked, else why not (for the LLM and log).
    public static func Run(player: ref<PlayerPuppet>, system: ref<CapriSystem>) -> String {
        if !IsDefined(player) || !IsDefined(system) {
            return "not ready";
        }
        if !system.MassOverrideShown() {
            return "Capri is not out right now: she has to be summoned first";
        }
        let now = system.Now();
        let last = CapriStorage.Get().massOverrideLastAt;
        if last > 0.0 && now - last < CapriMassOverride.Cooldown() {
            return "Mass Override is recharging";
        }
        if CapriActions.Ram(player) < CapriMassOverride.ChargeCost() {
            return "not enough battery charge for Mass Override";
        }
        let targets = MassOverrideSweep.Collect(player, CapriMassOverride.Radius(), CapriMassOverride.Cap());
        if ArraySize(targets) == 0 {
            return "nothing to change around V";
        }
        CapriStorage.Get().massOverrideLastAt = now;
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
