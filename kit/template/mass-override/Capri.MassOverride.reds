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

import Codeware.*
import RedHttpClient.*

public class CapriMassOverride extends IScriptable {

    // Battery charge per cast, taken from the RAM pool (placeholder value).
    public static func ChargeCost() -> Float { return 25.0; }

    // Targets one cast may change. The probe budget in MassOverrideProbe bounds
    // how far the fill walks; this bounds how much it may change.
    public static func Cap() -> Int32 { return 1000; }

    // How long people stay hostile and the block stays lit or dark before it reverts.
    public static func Duration() -> Float { return 30.0; }

    // How long before the next cast may be paid for. The gate keeps the same clock
    // per player (mass-override/gate.js, 40_000 ms); without it here the game would
    // let V cast as fast as RAM allows while the server refused the same casts.
    // 40 s: the 30 s effect and its revert, plus a margin. It was a 120 s placeholder,
    // which silently swallowed two test casts in Corpo Plaza 74 s and 107 s after one in
    // North Oak.
    public static func Cooldown() -> Float { return 40.0; }

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
    // Whether the multiplayer feed is wired. It is not yet, so every cast logs feed=unwired.
    public static func FeedLabel() -> String { return MassOverrideFeed.Label(); }

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
            MassOverrideLog.Write("cast stopped: not ready");
            return "not ready";
        }
        let game: GameInstance = player.GetGame();
        let playerId: String = EntityID.ToDebugString(player.GetEntityID());
        let cost: Float = CapriMassOverride.Cost();
        let ram: Float = CapriActions.Ram(player);
        MassOverrideLog.Write("cast entered build=" + MassOverrideBuild.Version() + " cost=" + ToString(RoundF(cost)) + " ram=" + ToString(RoundF(ram)) + " mode=" + ToString(mode));
        if cost > 0.0 && ram < cost {
            MassOverrideLog.Write("cast stopped: not enough battery charge");
            MassOverrideLog.Flush(game, playerId, "stopped");
            // On screen, not only in her transcript: Note() alone is invisible in play.
            system.Alert("Mass Override needs " + ToString(RoundF(cost)) + " battery charge, V has " + ToString(RoundF(ram)) + ".");
            return "not enough battery charge for Mass Override";
        }
        let started: Float = EngineTime.ToFloat(GameInstance.GetSimTime(game));
        // The recharge is part of the cast, not a courtesy: a session can pay RAM for
        // one cast per cooldown, the same as the gate charges.
        let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
        if IsDefined(prefs) && prefs.Casts() > 0 {
            let waited: Float = started - prefs.LastCastAt();
            if waited < CapriMassOverride.Cooldown() {
                let left: Int32 = RoundF(CapriMassOverride.Cooldown() - waited);
                MassOverrideLog.Write("cast stopped: recharging " + ToString(left) + "s (waited " + ToString(RoundF(waited)) + "s)");
                MassOverrideLog.Flush(game, playerId, "stopped");
                system.Alert("Mass Override is recharging: " + ToString(left) + " s left.");
                return "Mass Override is still recharging: " + ToString(left) + "s";
            }
        }
        // The run on screen (an earlier cast's, or another player's run here) is put back first: this
        // cast saves the street as it is, not halfway through a beat.
        MassOverrideRevert.EndActive(game, "a new cast here");
        let stats: ref<MassOverrideStats> = new MassOverrideStats();
        // Probes chain outward from V, so this reaches past 40 m and around corners.
        let targets = MassOverrideProbe.Collect(player, CapriMassOverride.Cap(), stats);
        MassOverrideLog.Write("probe targets=" + ToString(ArraySize(targets)) + " probes=" + ToString(stats.probes) + " parts=" + ToString(stats.parts) + " people=" + ToString(stats.people) + " devices=" + ToString(stats.devices) + " cacheHit=" + ToString(stats.cacheHit));
        // No early return on an empty sweep: the city's lights and the crowd's panic need no
        // target, and a cast that stopped here sent no report at all -- which looked exactly
        // like the action never running.
        if ArraySize(targets) == 0 {
            MassOverrideLog.Write("probe found nothing near V; city lights and panic still run");
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
        // Every game follows the gate's feed from the start of its session (MassOverrideRegistry);
        // a session that started none gets one now.
        MassOverrideFeed.Ensure(game);
        let blackout: Bool = mode == MassOverrideMode.Blackout();
        // Tell the gate about this cast: it keeps this game's recharge and hands the cast -- where V
        // stands, the mode this game runs, its token -- to every other game in the session, which runs
        // it too (MassOverrideRemote). The local cast below still runs if the server is unreachable.
        let token: String = "";
        if IsDefined(prefs) {
            token = prefs.NewToken();
        }
        MassOverrideCastPost.Register(game, playerId, MassOverrideCastPost.Body(player, targets, blackout ? "blackout" : "blink", token));
        stats.classes = MassOverrideProbe.Classes(targets);
        // The city's own lights: street lamps, building lights and neon answer to the city
        // light system, not to anything a probe reaches one at a time. Blink opens with
        // them forced on, blackout forced off; the beat keeps switching them from there.
        stats.cityBefore = MassOverrideCity.StateName(game);
        stats.cityFuses = MassOverrideCity.Fuses(game);
        stats.cityLights = MassOverrideCity.Lights(game);
        stats.hour = MassOverrideCity.Hour(game);
        if blackout {
            stats.cityForced = MassOverrideCity.Dark(game);
        } else {
            stats.cityForced = MassOverrideCity.Lit(game);
        }
        // The crowd: the panic MaxTac's arrival causes, broadcast from V.
        stats.terror += MassOverridePeople.Panic(player);
        stats.area = MassOverrideArea.Name(game, player.GetWorldPosition());
        stats.nearestCut = -1.0;
        stats.nearestHack = -1.0;
        // The beat's shared state: what it switches and recolours, and when it must stop
        // (a little before the revert, MassOverrideRun).
        let run: ref<MassOverrideRun> = MassOverrideRun.Start(game, CapriMassOverride.Duration());
        // People turn on V and are scared by name; cars, machines, screens and lights are hacked
        // (MassOverrideApply: the same for another player's cast run on another screen).
        MassOverrideApply.Targets(game, player, targets, run, stats, blackout, true);
        // Billboards, ad screens and wall screens are ink, not devices: the world ink layers'
        // roots and the world widgets go on the same beat (MassOverrideInk). The first beat
        // lands now, with the cast, and V's own screen glitches as the wave goes out.
        let inkLine: String = MassOverrideInk.Collect(run, stats);
        MassOverrideLog.Write("ink " + inkLine + " taken=" + ToString(ArraySize(run.ink))
            + " lightComponents=" + ToString(ArraySize(run.lights)));
        MassOverrideInk.Beat(run, !blackout, 1.0, 0);
        MassOverrideLights.Beat(run, !blackout, 1.0, 0);
        MassOverrideFx.Burst(game, player, 1.5);
        // The counts go to the gate over HTTP. A cast that throws inside the loop above
        // never reaches this, so a missing report is itself the diagnosis.
        MassOverrideCastPost.Report(game, "{\"phase\":\"cast\",\"playerId\":" + MassOverrideLog.Quote(playerId)
            + ",\"token\":" + MassOverrideLog.Quote(token)
            + ",\"build\":\"" + MassOverrideBuild.Version() + "\""
            + ",\"mode\":\"" + (blackout ? "blackout" : "blink") + "\""
            + ",\"probes\":" + ToString(stats.probes)
            + ",\"parts\":" + ToString(stats.parts)
            + ",\"people\":" + ToString(stats.people)
            + ",\"hostile\":" + ToString(stats.hostile)
            + ",\"crowd\":" + ToString(stats.crowd)
            + ",\"terror\":" + ToString(stats.terror)
            + ",\"devices\":" + ToString(stats.devices)
            + ",\"vehicles\":" + ToString(stats.vehicles)
            + ",\"changed\":" + ToString(stats.changed)
            + ",\"glitched\":" + ToString(stats.glitched)
            + ",\"emp\":" + ToString(stats.emp)
            + ",\"strobed\":" + ToString(stats.strobed)
            + ",\"strobeLitBefore\":" + ToString(stats.strobeLitBefore)
            + ",\"notHacked\":" + ToString(stats.notHacked)
            + ",\"accelerated\":" + ToString(stats.accelerated)
            + ",\"alarms\":" + ToString(stats.alarms)
            + ",\"honks\":" + ToString(stats.honks)
            + ",\"hackInView\":" + ToString(stats.hackInView)
            + ",\"nearestHack\":" + ToString(RoundF(stats.nearestHack))
            + ",\"inkLayers\":" + ToString(stats.inkLayers)
            + ",\"worldWidgets\":" + ToString(stats.worldWidgets)
            + ",\"inkTargets\":" + ToString(ArraySize(run.ink))
            + ",\"lightComponents\":" + ToString(ArraySize(run.lights))
            + ",\"inkNames\":" + MassOverrideLog.Quote(stats.inkNames)
            + ",\"city\":\"" + stats.cityBefore + "\""
            + ",\"cityForced\":" + (stats.cityForced ? "true" : "false")
            + ",\"cityFuses\":" + ToString(stats.cityFuses)
            + ",\"cityLights\":" + ToString(stats.cityLights)
            + ",\"hour\":" + ToString(stats.hour)
            + ",\"registry\":" + ToString(stats.registry)
            + ",\"registryNear\":" + ToString(stats.registryNear)
            + ",\"attachEvents\":" + ToString(stats.attachEvents)
            + ",\"classes\":" + MassOverrideLog.Quote(stats.classes)
            + ",\"area\":" + MassOverrideLog.Quote(stats.area)
            + ",\"cooldown\":" + ToString(RoundF(CapriMassOverride.Cooldown()))
            + ",\"cap\":" + ToString(CapriMassOverride.Cap()) + "}");
        // The beat: both modes stop a little before the revert (MassOverrideRun).
        if blackout {
            let hold: ref<MassOverrideHold> = new MassOverrideHold();
            hold.game = game;
            hold.player = player;
            hold.targets = targets;
            hold.run = run;
            hold.tick = 1;
            GameInstance.GetDelaySystem(game).DelayCallback(hold, MassOverrideHold.Interval(), false);
        } else {
            // The cast switched every light on; the first pulse switches them off.
            let pulse: ref<MassOverridePulse> = new MassOverridePulse();
            pulse.game = game;
            pulse.player = player;
            pulse.targets = targets;
            pulse.run = run;
            pulse.tick = 1;
            pulse.lit = false;
            GameInstance.GetDelaySystem(game).DelayCallback(pulse, MassOverridePulse.Interval(), false);
        }
        // What the cast did, on screen: before this, a cast that ran and one that never
        // happened looked the same to V.
        system.Alert("Mass Override: " + ToString(stats.glitched) + " machines hacked, "
            + ToString(stats.worldWidgets + stats.inkLayers) + " billboards and screens and "
            + ToString(stats.strobed) + " lights " + (blackout ? "failing" : "strobing") + ", "
            + ToString(stats.accelerated) + " cars hijacked, " + ToString(stats.alarms) + " alarms, "
            + ToString(stats.crowd) + " people panicking.");
        // Pictures of what V sees, a few seconds in and again after the revert, kept in
        // Capri's storage for comparison (CapriMassOverrideShot).
        let shotTag: String = "mass_override_" + ToString(IsDefined(prefs) ? prefs.Casts() : 0);
        // "before" is the picture Capri took when V asked, a second or two ago; the others
        // are asked for now, into the effect and after its revert.
        CapriMassOverrideShot.SaveLast(shotTag + "_before");
        CapriMassOverrideShot.Schedule(game, shotTag + "_during", 3.0);
        CapriMassOverrideShot.Schedule(game, shotTag + "_during2", 15.0);
        CapriMassOverrideShot.Schedule(game, shotTag + "_after", CapriMassOverride.Duration() + 3.0);
        // Revert on a delay, not on Capri: dismissing her does not end it early.
        let revert: ref<MassOverrideRevert> = new MassOverrideRevert();
        revert.game = game;
        revert.player = player;
        revert.targets = targets;
        revert.playerId = playerId;
        revert.run = run;
        MassOverrideRevert.Arm(game, revert, CapriMassOverride.Duration());
        // What actually took, read back once the queued switches have run, again after
        // the revert, and once more after the last picture so its line is sent too.
        let verify: ref<MassOverrideVerify> = new MassOverrideVerify();
        verify.game = game;
        verify.playerId = playerId;
        verify.phase = "verify";
        verify.mode = blackout ? "blackout" : "blink";
        verify.targets = targets;
        GameInstance.GetDelaySystem(game).DelayCallback(verify, MassOverrideVerify.Delay(), false);
        let settled: ref<MassOverrideVerify> = new MassOverrideVerify();
        settled.game = game;
        settled.playerId = playerId;
        settled.phase = "settled";
        settled.mode = blackout ? "blackout" : "blink";
        settled.targets = targets;
        GameInstance.GetDelaySystem(game).DelayCallback(settled, CapriMassOverride.Duration() + MassOverrideVerify.Delay(), false);
        let closing: ref<MassOverrideVerify> = new MassOverrideVerify();
        closing.game = game;
        closing.playerId = playerId;
        closing.phase = "final";
        closing.mode = blackout ? "blackout" : "blink";
        closing.targets = targets;
        GameInstance.GetDelaySystem(game).DelayCallback(closing, CapriMassOverride.Duration() + 10.0, false);
        stats.seconds = EngineTime.ToFloat(GameInstance.GetSimTime(game)) - started;
        if CapriMassOverride.Instrumented() {
            // One grep-able line per cast. A fill happens in a single frame, so `secs` can
            // honestly read 0.000.
            let services: String = MassOverrideDiag.Describe();
            MassOverrideLog.Write("mode=" + (blackout ? "blackout" : "blink")
                + " modeSource=" + CapriMassOverride.ModeSource()
                + " pin=" + CapriMassOverride.PinLabel()
                + " cost=" + ToString(RoundF(cost))
                + " ram=" + ToString(ramBefore)
                + " area=" + stats.area
                + " cache=" + (stats.cacheHit ? "hit" : "miss")
                + " probes=" + ToString(stats.probes)
                + " people=" + ToString(stats.people)
                + " crowd=" + ToString(stats.crowd)
                + " devices=" + ToString(stats.devices)
                + " vehicles=" + ToString(stats.vehicles)
                + " glitched=" + ToString(stats.glitched)
                + " emp=" + ToString(stats.emp)
                + " strobed=" + ToString(stats.strobed)
                + " notHacked=" + ToString(stats.notHacked)
                + " accelerated=" + ToString(stats.accelerated)
                + " alarms=" + ToString(stats.alarms)
                + " honks=" + ToString(stats.honks)
                + " inView=" + ToString(stats.hackInView)
                + " terror=" + ToString(stats.terror)
                + " city=" + stats.cityBefore + (blackout ? "->forcedOff" : "->forcedOn")
                + " hour=" + ToString(stats.hour)
                + " registry=" + ToString(stats.registry)
                + " classes=" + stats.classes
                + " targets=" + ToString(ArraySize(targets))
                + " secs=" + ToString(stats.seconds)
                + " services=" + services
                + " feed=" + CapriMassOverride.FeedLabel());
            if !MassOverrideDiag.AllPresent() && MassOverrideDiag.ShouldWarn(game) {
                MassOverrideLog.Write("service missing: " + services);
            }
        }
        MassOverrideLog.Flush(game, playerId, "cast");
        return "";
    }
}

// EYES. Capri Voz already takes pictures of the game window for Capri (Capri.Player2.reds:
// Look): the game writes vista_pedido.json, Capri Voz answers in vista_respuesta.json and
// leaves the picture in the file it names. A cast asks for one a few seconds into the
// effect and one after the revert, and keeps each as base64 text in Capri's storage
// (r6/storages/CapriConstruct/mass_override_<cast>_<before|during|during2|after>.txt), so what V actually
// saw can be checked without anyone describing it. Nothing is uploaded anywhere.
// Each poll is a new object, the way the pulses are, never the same one re-armed.
public class CapriMassOverrideShot extends DelayCallback {
    public let game: GameInstance;
    public let tag: String;
    public let id: String;
    public let since: Float;
    public let asked: Bool;

    // Keeps the last picture Capri Voz took (Capri looks when V asks), under `tag`.
    public static func SaveLast(tag: String) -> Void {
        let storage: ref<CapriStorage> = CapriStorage.Get();
        if !IsDefined(storage) { return; }
        let reply = storage.ReadFile("vista_respuesta.json");
        if !IsDefined(reply) || !Equals(reply.GetKeyString("estado"), "listo") {
            MassOverrideLog.Write("shot " + tag + ": no earlier picture");
            return;
        }
        let picture: String = storage.ReadBase64(reply.GetKeyString("archivo"));
        storage.WriteFile(tag + ".txt", picture);
        MassOverrideLog.Write("shot " + tag + " saved from look id=" + reply.GetKeyString("id") + " chars=" + ToString(StrLen(picture)));
    }

    public static func Schedule(game: GameInstance, tag: String, delay: Float) -> Void {
        let shot: ref<CapriMassOverrideShot> = new CapriMassOverrideShot();
        shot.game = game;
        shot.tag = tag;
        GameInstance.GetDelaySystem(game).DelayCallback(shot, delay, false);
    }

    public func Call() -> Void {
        let storage: ref<CapriStorage> = CapriStorage.Get();
        if !IsDefined(storage) { return; }
        let now: Float = EngineTime.ToFloat(GameInstance.GetSimTime(this.game));
        if !this.asked {
            // A number, as Capri's own look ids are, and far above her counter.
            let id: String = ToString(770000000 + RoundF(now * 10.0));
            storage.WriteFile("vista_pedido.json", "{\"id\":\"" + id + "\",\"ancho\":1024}");
            this.Next(id, now, 0.15);
            return;
        }
        let reply = storage.ReadFile("vista_respuesta.json");
        if IsDefined(reply) && Equals(reply.GetKeyString("id"), this.id) {
            if Equals(reply.GetKeyString("estado"), "listo") {
                let picture: String = storage.ReadBase64(reply.GetKeyString("archivo"));
                storage.WriteFile(this.tag + ".txt", picture);
                MassOverrideLog.Write("shot " + this.tag + " saved chars=" + ToString(StrLen(picture)));
            } else {
                MassOverrideLog.Write("shot " + this.tag + " not taken: " + reply.GetKeyString("estado"));
            }
            return;
        }
        if now - this.since > 4.0 {
            MassOverrideLog.Write("shot " + this.tag + ": Capri Voz did not answer");
            return;
        }
        this.Next(this.id, this.since, 0.1);
    }

    private func Next(id: String, since: Float, delay: Float) -> Void {
        let next: ref<CapriMassOverrideShot> = new CapriMassOverrideShot();
        next.game = this.game;
        next.tag = this.tag;
        next.id = id;
        next.since = since;
        next.asked = true;
        GameInstance.GetDelaySystem(this.game).DelayCallback(next, delay, false);
    }
}
