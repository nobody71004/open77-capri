import RedHttpClient.*

// Mass Override: the probe sweep, the per-area cache and the effects.
//
// EVERY CLIENT RUNS EVERY CAST (1.16.17). Up to 1.16.16 a cast showed on the caster's screen
// alone: the feed poller only started on a game after that game had cast once, it only carried
// the mode for that game's NEXT cast, and every game registered with the gate under its V's
// entity id -- the same on every PC -- so one player's recharge held everyone's cast at the gate.
// Now each game polls its gate from the moment its session starts (MassOverrideRegistry.OnAttach,
// MassOverrideFeed), under an id of its own (MassOverridePrefs.Session); a cast carries where the
// caster stood, the mode the caster's game runs and a token; and every other game runs it
// (MassOverrideRemote): the city's lights and the billboards for everyone in the session, the
// street around the cast -- machines, lights, cars, the crowd's panic -- within StreetReach() of
// it, for the time the cast has left. Nobody is turned on a V who did not cast, and nothing is
// charged. One run is on screen at a time (MassOverrideRevert.EndActive): the next cast, here or
// anyone's, first puts the street back as it was.
//
// WHAT THE STREET SHOWS (1.16.15). Two 1.16.14 casts in Japantown did what they
// reported -- 21 machines glitching, 42 lights switching, 4 cars floored, horns -- and
// the street still looked the same, because what makes it bright is not devices: the
// billboards and ad screens are world advertisement nodes drawn by the ink
// advertisements layer, and the screens on walls and machines are world widgets. None
// of them has a device controller; all of them are ink. Codeware hands out the ink
// system's layers and its world widgets (inkSystem.GetLayers / GetWorldWidgets), so the
// beat now blinks and recolours those roots too (MassOverrideInk), every light
// component on a hacked device pulses in hacker colours through the call the game's
// own ChangeLightEvent ends in (gameLightComponent.SetParameters, MassOverrideLights),
// and V's screen glitches as the wave goes out and again as the city comes back
// (transition_glitch_loop, the fast-forward glitch; MassOverrideFx). Every opacity,
// tint and light setting is saved at the cast and put back at the revert.
//
// WHAT A CAST CHANGES (1.16.14). The 1.16.13 casts did everything they reported -- 66
// devices without power, 8 car alarms ringing, 47 lights and screens that had been on
// -- and nobody standing in Japantown at 8 in the morning could tell: a vending machine
// with its screen off and a street lamp that was already off by day look like nothing
// happened. Every lever is now one the game plays when V hacks something:
//   machines, screens  the device's own glitch (QuestStartGlitch -> StartGlitching): a
//                      vending machine throws cans out, ads and TVs break up, with the
//                      glitch sound; plus the EMP grenade's sparks (EMPHitEvent)
//   lights             switched ON and OFF on a beat through their own controllers
//                      (SetDeviceON / SetDeviceOFF), which lights a street lamp the
//                      timetable keeps off by day; the city light system strobes too
//   cars               a car with crowd at the wheel gets V's Accelerate quickhack and
//                      high-priority panic driving, and its alarm; a parked car its alarm
//   people             the Terror stim and hostility, renewed every few seconds
// The revert stops each glitch, puts every light back in the state it had, silences
// the alarms, calms the people and removes the city request (MassOverrideHack,
// MassOverrideCars, MassOverrideRevert). The step log goes to the gate (phase "log"):
// a second FileSystem.GetStorage("CapriConstruct") revokes Capri's own storage.
//
// WHAT A CAST CHANGED (1.16.11 - 1.16.13). A live cast on 1.16.10 switched 243 components on 50
// devices in Japantown and nobody could see it: the devices were vending machines,
// door panels and traffic lights, and a disabled widget or light component is not
// what makes a street bright. Every lever is now one the game itself uses:
//   city lights  the City Light System's forced state (MassOverrideCity), the switch
//                weather and quests use for every street lamp, building light and
//                neon sign on a fuse;
//   devices      SetDeviceUnpowered on each device's own controller
//                (MassOverridePower), the fuse-box power cut;
//   people       a Terror stim, the panic MaxTac's arrival causes (MassOverridePeople);
//   cars         the car alarm, or the horn of an occupied car (MassOverrideCars);
// and the devices no targeting query returns come from an attach registry
// (MassOverrideRegistry). Each cast reports what it asked for, what took two seconds
// later, and what the revert put back (phase cast / verify / revert / settled).
// The notes below describe the original component pass, which is kept for the probe
// and the cache.
//
// HOSTILITY is the same call Open77PlayerModels.reds uses:
// AttitudeAgent.SetAttitudeTowards(EAIAttitude.AIA_Hostile).
//
// SCREENS, BILLBOARDS, TVs go through the component switch the vanilla device
// classes themselves use. In the source that ships with REDmod
// (tools/redmod/scripts):
//   cyberpunk/devices/billboard/billboard.script    -> m_advUiComponent.Toggle(bool)
//   cyberpunk/devices/homeAppliances/.../tv.script  -> m_uiComponent.Toggle(bool)
//   cyberpunk/devices/lcdScreens/lcdScreen.script   -> m_uiComponent.Toggle(bool)
// so this is the game's own switch, not a guess. The widget component NAME
// differs per device ('ui', 'ads', 'tv_ui', 'radio_ui', 'terminalui'), so
// components are chosen by class instead of by name.
//
// LIGHTS use the same component enable switch, on the gameLightComponent that
// ElectricLight requests for a street light or a lamp. vehicleLightComponent
// derives from it, so headlights match too. Traffic lights get their red, yellow
// and green from light components on the device (trafficLight.script names them
// in ToggleLightByNameEvent), so they darken through the same switch.
//
// EVERY TYPE IS CHECKED AGAINST THE 2.31 RTTI TABLE that ships with the Red4ext
// plugin (red4ext/plugins/Open77/rtti-manifest-2.31.json), which is the engine's
// own list of what a script may name:
//   IWorldWidgetComponent      class, parent WidgetBaseComponent, native, abstract
//   AdvertisementWidgetComponent class, parent IWorldWidgetComponent  (billboards)
//   gameLightComponent         class, parent entLightComponent, native
//   vehicleLightComponent      class, parent gameLightComponent       (headlights)
//   vehicleBaseObject          class, parent gameObject                (cars)
//   VehicleObject              the script-side vehicle class Capri already casts to
//   ScriptableService          class, parent IScriptable, abstract    (the cache)
// So the screen test is one cast for billboards, LCD screens, TVs and vending ads,
// and the light test covers street lamps, traffic lights and vehicle lights.
//
// SWITCHING A LIGHT is not the same as switching a screen. A screen is the
// component itself (vanilla: m_uiComponent.Toggle(false)), but a light is switched
// by its own state: gameLightComponent has ToggleLight(on, loop) and IsOn() in the
// RTTI table, and the vanilla billboard instead queues a ToggleLightEvent
// (evt.toggle = on) to the entity. Component disable alone is what a blackout was
// fighting against, because a controller can enable the component again; the light
// state and the event both stick. Both are used here.
// What that table does NOT contain, and therefore proves nothing about, is a
// vehicle flag in TSFMV (it lists only Obj_Puppet, Obj_Player, Obj_Device,
// Obj_Sensor and Obj_Other), so whether a probe returns a car is settled by the
// per-cast `vehicles=` count in a running game, not here.
//
// TWO MODES: Blink pulses everything it found for the whole duration, which reads
// as an overload; Blackout holds it dark, which reads as a power cut. Blink is the
// default and both are kept, because a blackout in the middle of a chase reads
// differently from a strobing street.
//
// CACHE: the devices a fill found are kept per area, so a second flood in the same
// block does not walk the street again. People are never cached: they move, so a
// cache hit re-reads them with a single probe.
//
// Local test build only.

public class MassOverrideTarget {
  public let entityId: EntityID;
  public let kind: Int32;   // 0 = person, 1 = screen, 2 = light, 3 = vehicle
  public let label: String; // class name, for the log
  public let area: String;  // 50 m cell the target stands in
  // What each part was doing before the cast touched it, so the revert puts it
  // back rather than switching the whole street on. A newsstand screen that was
  // already dark, or a lamp that was already off, stays that way.
  public let screenWasOn: Bool;
  public let lightWasOn: Bool;
  // What this cast did to it through the game's own systems, so the revert undoes
  // exactly that and nothing else.
  public let cut: Bool;   // unpowered through its own controller (MassOverridePower)
  public let alarm: Bool; // car alarm switched on (MassOverrideCars)
  // The controller this cast cut, kept so the power comes back even when the device has
  // streamed out by the revert: a cast in North Oak followed by a fast travel left 20
  // devices without power, because the revert could no longer find a single one of them.
  public let ps: ref<ScriptableDeviceComponentPS>;
  // 1.16.14: what the hack did, so the revert undoes exactly that (MassOverrideHack).
  public let glitch: Bool;  // its own glitch started through its controller
  public let emp: Bool;     // EMP sparks queued; they end themselves after their lifetime
  public let strobe: Bool;  // switched ON and OFF on the beat
  public let stateOn: Bool; // the strobed device was ON at the cast: the revert puts that back
  public let hacked: Bool;  // a crowd-driven car given the Accelerate quickhack
}

// Kept as Int32 constants rather than an enum so the mode can be passed through a
// DelayCallback field and compared with a plain != , which compiles everywhere.
public class MassOverrideMode {
  // Pulse the lights and screens for the duration. Default.
  public static func Blink() -> Int32 { return 0; }
  // Hold them dark for the duration, then restore.
  public static func Blackout() -> Int32 { return 1; }
}

// Int32 constants for the same reason the modes are: they travel through a
// cached entry and are compared with != , which compiles everywhere.
// Runtime diagnostics. Each stage of a cast is written with FTLog and kept in memory
// (MassOverridePrefs), and the lines go to the gate with the cast's reports (phase
// "log", MassOverrideLog.Flush), so a cast that stops early says where it stopped.
// They used to be appended to r6/storages/CapriConstruct/mass_override.log, which never
// appeared -- and could not: RedFileSystem lets one caller open a storage, and answers a
// second FileSystem.GetStorage("CapriConstruct") by revoking that storage for the rest
// of the session (red4ext/logs/redfilesystem-*.log: "Access to this storage has been
// permanently revoked"). Capri opens it at start-up, so the first line of the first cast
// locked Capri herself out of her settings, her history and the files Capri Voz answers
// in. Nothing here opens a storage any more.
public class MassOverrideLog {
  public static func Enabled() -> Bool { return true; }
  // Lines kept between flushes; the oldest go first.
  public static func Keep() -> Int32 { return 120; }

  public static func Write(line: String) -> Void {
    if !MassOverrideLog.Enabled() { return; }
    FTLog("[MassOverride] " + line);
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if IsDefined(prefs) {
      prefs.PushLog(line, MassOverrideLog.Keep());
    }
  }

  // A JSON string: backslashes first, then quotes.
  public static func Quote(text: String) -> String {
    let out: String = StrReplaceAll(text, "\\", "\\\\");
    out = StrReplaceAll(out, "\"", "\\\"");
    return "\"" + out + "\"";
  }

  // Sends the lines written since the last flush to the gate, and forgets them.
  public static func Flush(game: GameInstance, playerId: String, at: String) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if !IsDefined(prefs) { return; }
    let lines: array<String> = prefs.TakeLog();
    if ArraySize(lines) == 0 { return; }
    // playerId is V's entity id -- the same on every PC -- so the session says which game this is
    let body: String = "{\"phase\":\"log\",\"playerId\":" + MassOverrideLog.Quote(playerId)
      + ",\"session\":" + MassOverrideLog.Quote(prefs.Session())
      + ",\"build\":\"" + MassOverrideBuild.Version() + "\""
      + ",\"at\":" + MassOverrideLog.Quote(at)
      + ",\"lines\":[";
    let i: Int32 = 0;
    while i < ArraySize(lines) {
      if i > 0 { body += ","; }
      body += MassOverrideLog.Quote(lines[i]);
      i += 1;
    }
    MassOverrideCastPost.Report(game, body + "]}");
  }
}

// Int32 constants for the same reason the modes are: they travel through a
// cached entry and are compared with != , which compiles everywhere.
public class MassOverrideKind {
  public static func Person() -> Int32 { return 0; }
  // Billboard, TV, LCD screen, vending-machine ad: anything with a world widget.
  public static func Screen() -> Int32 { return 1; }
  // Street lamp, traffic light, neon fitting: anything with a gameLightComponent.
  public static func Light() -> Int32 { return 2; }
  // A car: lights plus, sometimes, dashboard widgets. Its own kind so the log can
  // say whether a probe reached any.
  public static func Vehicle() -> Int32 { return 3; }
}

// Which switch actually moved a light, as bit values so a light that needed both
// paths can say so. This is what tells whether the entity event and the light's own
// state are carrying a blackout, or whether the component fallback is doing all the
// work on its own.
public class MassOverrideLightSwitch {
  public static func None() -> Int32 { return 0; }
  public static func State() -> Int32 { return 1; }     // ToggleLight moved it
  public static func Component() -> Int32 { return 2; } // only the component switch did
  public static func Both() -> Int32 { return 3; }
}

// Which mode a cast uses. This is Mass Override's own state: no Capri setting, no
// other Capri file, no keybind and no item.
//
// The mode is chosen per cast, one cast at a time, and the sequence starts with
// blackout: the first cast is visible as shipped and needs no edit to test, and each
// cast after it flips, blackout then blink. Pin() fixes one mode for every cast
// until Auto() resumes alternating. Nothing else in the game can select it: Capri's
// settings are her quickhack tier, which is not a visual mode, and her action table
// does not dispatch here yet.
public class MassOverridePrefs extends ScriptableService {
  private let m_pinned: Int32 = -1; // -1 = alternate, 0 = blink, 1 = blackout
  private let m_next: Int32 = 0;    // what the next unpinned cast uses (0 = blink: the beat reads at once)
  private let m_serverMode: Int32 = -1; // mode a server broadcast named, waiting for its cast
  private let m_lastCastAt: Float = 0.0; // sim time of the last charged cast
  private let m_casts: Int32;           // casts charged so far; 0 means none yet
  private let m_lastFromServer: Bool;   // the last Mode() came from a broadcast, not the cursor
  private let m_feedRunning: Bool;      // the feed poller is already running this session
  private let m_feedGen: Int32;         // the poller in charge: a new game session starts a new one, older ones end
  private let m_session: String;        // this running game's own id at the gate, made once: every PC's V has the
                                        // same entity id, so that id alone made every player one player there
  private let m_tokens: Int32;          // tokens handed out, one per cast this game sent
  private let m_ownTokens: array<String>; // the casts this game sent: the feed hands them back, not run twice
  private let m_active: ref<MassOverrideRevert>; // the run on screen now, this game's or another player's
  private let m_activeIds: Int32;       // runs put on screen so far (each revert's id)
  private let m_remoteRuns: Int32;      // other players' casts run here
  private let m_warnedMissing: Bool; // the one-time "service missing" line was printed
  private let m_log: array<String>;  // step log lines not yet sent (MassOverrideLog)
  private let m_logDropped: Int32;   // lines dropped since the last flush, buffer full

  public static func Get() -> ref<MassOverridePrefs> {
    let service: ref<MassOverridePrefs> =
      GameInstance.GetScriptableServiceContainer().GetService(n"MassOverridePrefs") as MassOverridePrefs;
    if IsDefined(service) { return service; }
    return GameInstance.GetScriptableServiceContainer().GetService(n"Open77.MassOverridePrefs") as MassOverridePrefs;
  }

  // Each cast consumes one: this is the per-cast choice. A null service leaves the
  // caller on blink, so the fallback is the old behaviour rather than no effect.
  // A broadcast mode is taken first: the server owns the beat for the whole session,
  // so a client must not advance its own cursor past what everyone else is running.
  // The pin and the local cursor only apply when no broadcast is waiting.
  // The feed poller owns its own lifetime, so it must only be started once.
  public func FeedRunning() -> Bool { return this.m_feedRunning; }
  public func MarkFeedRunning() -> Void { this.m_feedRunning = true; }

  // The poller in charge; a new one (a new game session) makes the one before it stop at its next tick.
  public func FeedGen() -> Int32 { return this.m_feedGen; }
  public func NextFeedGen() -> Int32 {
    this.m_feedGen += 1;
    this.m_feedRunning = true;
    return this.m_feedGen;
  }

  // This running game's id at the gate: random, made at its first use, kept for the game's life.
  public func Session() -> String {
    if StrLen(this.m_session) == 0 {
      this.m_session = "s" + ToString(RandRange(100000, 999999)) + ToString(RandRange(100000, 999999));
    }
    return this.m_session;
  }

  // The token of the next cast this game sends, remembered (the last 16) so the feed's copy is not run here.
  public func NewToken() -> String {
    this.m_tokens += 1;
    let token: String = this.Session() + "-" + ToString(this.m_tokens);
    ArrayPush(this.m_ownTokens, token);
    if ArraySize(this.m_ownTokens) > 16 {
      ArrayErase(this.m_ownTokens, 0);
    }
    return token;
  }

  public func IsOwnToken(token: String) -> Bool { return ArrayContains(this.m_ownTokens, token); }

  // The run on screen (MassOverrideRevert.EndActive puts it back before the next one starts).
  public func Active() -> ref<MassOverrideRevert> { return this.m_active; }
  public func SetActive(revert: ref<MassOverrideRevert>) -> Int32 {
    this.m_activeIds += 1;
    this.m_active = revert;
    return this.m_activeIds;
  }

  public func CountRemote() -> Int32 {
    this.m_remoteRuns += 1;
    return this.m_remoteRuns;
  }

  public func Mode() -> Int32 {
    let served: Int32 = this.TakeServerMode();
    if served >= 0 { return served; }
    if this.m_pinned >= 0 { return this.m_pinned; }
    let mode: Int32 = this.m_next;
    if mode == MassOverrideMode.Blink() {
      this.m_next = MassOverrideMode.Blackout();
    } else {
      this.m_next = MassOverrideMode.Blink();
    }
    return mode;
  }

  // Called by the multiplayer layer when a cast arrives carrying the mode the server
  // broadcast. It is held for exactly one cast, so a cast that never runs locally
  // cannot leave a mode behind for the next one. Anything that is not a real mode is
  // ignored rather than stored.
  public func ReceiveServerMode(mode: Int32) -> Void {
    if mode != MassOverrideMode.Blink() && mode != MassOverrideMode.Blackout() { return; }
    this.m_serverMode = mode;
  }

  // -1 when nothing is waiting; otherwise the broadcast mode, consumed.
  public func TakeServerMode() -> Int32 {
    if this.m_serverMode < 0 {
      this.m_lastFromServer = false;
      return -1;
    }
    let mode: Int32 = this.m_serverMode;
    this.m_serverMode = -1;
    this.m_lastFromServer = true;
    return mode;
  }

  // Whether the last cast took its mode from a broadcast. Read for the cast log line.
  public func LastFromServer() -> Bool { return this.m_lastFromServer; }

  // The cooldown lives here rather than in a static because redscript has no static
  // fields, and here rather than in Capri's storage because it belongs to Mass
  // Override: the same service the gate's per-player clock mirrors.
  //
  // "Never cast" is a count of zero, not a -1 timestamp: a field initialiser must be a
  // constant, and redscript folds `-1` for Int32 but not `-1.0`, so a Float sentinel
  // fails to compile with INVALID_CONSTANT.
  public func LastCastAt() -> Float { return this.m_lastCastAt; }
  public func Casts() -> Int32 { return this.m_casts; }
  public func MarkCastAt(now: Float) -> Void {
    this.m_lastCastAt = now;
    this.m_casts = this.m_casts + 1;
  }

  public func Pin(mode: Int32) -> Void { this.m_pinned = mode; }

  public func Auto() -> Void { this.m_pinned = -1; }

  public func Pinned() -> Bool { return this.m_pinned >= 0; }

  // The pin as a word, for the cast log line: "none" while casts alternate, else the
  // mode Pin() fixed. A log that only named the mode could not tell a pinned blink
  // that happens to follow a blink from an alternating one.
  public func PinnedMode() -> String {
    if this.m_pinned == MassOverrideMode.Blink() { return "blink"; }
    if this.m_pinned == MassOverrideMode.Blackout() { return "blackout"; }
    return "none";
  }

  // Remembered here rather than in a static, because redscript has no static fields:
  // the first service that does register carries the flag for the ones that did not.
  public func WarnedMissing() -> Bool { return this.m_warnedMissing; }
  public func MarkWarnedMissing() -> Void { this.m_warnedMissing = true; }

  // The step log, kept here because redscript has no static fields.
  public func PushLog(line: String, keep: Int32) -> Void {
    if ArraySize(this.m_log) >= keep {
      ArrayErase(this.m_log, 0);
      this.m_logDropped += 1;
    }
    ArrayPush(this.m_log, line);
  }

  public func TakeLog() -> array<String> {
    let lines: array<String>;
    if this.m_logDropped > 0 {
      ArrayPush(lines, "(" + ToString(this.m_logDropped) + " earlier lines dropped)");
      this.m_logDropped = 0;
    }
    let i: Int32 = 0;
    while i < ArraySize(this.m_log) {
      ArrayPush(lines, this.m_log[i]);
      i += 1;
    }
    ArrayClear(this.m_log);
    return lines;
  }
}

// THE FEED. Every game polls its gate's GET /casts from the start of its session (one poller per
// session: MassOverrideRegistry.OnAttach starts it, a cast makes sure there is one) and runs every
// cast that is still on, the caster's own excepted (its token). The gate answers in plain text --
// no JSON parser in reach here: "<next>", then one line per cast still on, "<seq> <mode> <x cm>
// <y cm> <z cm> <age ms> <ms left> <token>" (whole numbers: StringToInt reads them).
public class MassOverrideFeed {
  // The gate this package talks to; the kit puts XyberRP's own in XyberRP's package.
  public static func Base() -> String { return "https://xyberrp.duckdns.org/mass-override-staging"; }
  public static func Url() -> String { return MassOverrideFeed.Base() + "/feed"; }
  public static func CastsUrl() -> String { return MassOverrideFeed.Base() + "/casts"; }
  // One poll every two seconds: another player's cast shows here within about that.
  public static func Interval() -> Float { return 2.0; }
  // A request that never came back is given up after this long, and the next one goes out.
  public static func StuckSeconds() -> Float { return 20.0; }
  // How near a cast this game runs its street as well (machines, lights, cars, the crowd). Farther
  // off only the city's lights and the billboards change: on the caster's screen those are the
  // whole city's too.
  public static func StreetReach() -> Float { return 150.0; }
  // False: a cast farther off than StreetReach() is not shown here at all.
  public static func CityWide() -> Bool { return true; }
  // A cast with less than this left is not started here.
  public static func MinSeconds() -> Float { return 2.0; }
  public static func Label() -> String { return "staging"; }

  // A poller for this game session; the one before it (an earlier session's) ends at its next tick.
  public static func Start(game: GameInstance, why: String) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if !IsDefined(prefs) {
      FTLog("[MassOverride] feed not started (" + why + "): the prefs service is missing");
      return;
    }
    let poll: ref<MassOverrideFeedPoll> = new MassOverrideFeedPoll();
    poll.game = game;
    poll.gen = prefs.NextFeedGen();
    poll.since = -1;
    GameInstance.GetDelaySystem(game).DelayCallback(poll, 1.0, false);
    MassOverrideLog.Write("feed started (" + why + ") gen=" + ToString(poll.gen) + " session=" + prefs.Session()
      + " gate=" + MassOverrideFeed.Label() + " every " + ToString(MassOverrideFeed.Interval()) + " s");
  }

  // A cast makes sure one runs (a session the registry started none for).
  public static func Ensure(game: GameInstance) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if IsDefined(prefs) && prefs.FeedGen() == 0 {
      MassOverrideFeed.Start(game, "cast");
    }
  }

  // A mode the server named, for this game's next cast (kept for CapriMassOverride.ReceiveServerMode).
  public static func Apply(game: GameInstance, mode: Int32) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if IsDefined(prefs) { prefs.ReceiveServerMode(mode); }
  }

  // One answer of GET /casts. The first answer of a session runs what is still on (a player who
  // arrives during a blackout sees the rest of it); after that the cursor keeps every cast to once.
  public static func Handle(game: GameInstance, text: String, poll: ref<MassOverrideFeedPoll>) -> Void {
    let lines: array<String> = StrSplit(text, "\n");
    if ArraySize(lines) == 0 { return; }
    let next: Int32 = StringToInt(lines[0]);
    let joining: Bool = poll.since < 0;
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    let i: Int32 = 1;
    while i < ArraySize(lines) {
      let f: array<String> = StrSplit(lines[i], " ");
      if ArraySize(f) == 8 {
        let seq: Int32 = StringToInt(f[0]);
        let token: String = f[7];
        let left: Float = Cast<Float>(StringToInt(f[6])) / 1000.0;
        if seq > poll.since {
          if IsDefined(prefs) && prefs.IsOwnToken(token) {
            MassOverrideLog.Write("feed seq=" + ToString(seq) + ": this game's own cast, already on screen");
          } else {
            if left < MassOverrideFeed.MinSeconds() {
              MassOverrideLog.Write("feed seq=" + ToString(seq) + ": " + ToString(RoundF(left)) + " s left, not started here");
            } else {
              let origin: Vector4;
              origin.X = Cast<Float>(StringToInt(f[2])) / 100.0;
              origin.Y = Cast<Float>(StringToInt(f[3])) / 100.0;
              origin.Z = Cast<Float>(StringToInt(f[4])) / 100.0;
              origin.W = 1.0;
              let mode: Int32 = MassOverrideMode.Blink();
              if Equals(f[1], "blackout") {
                mode = MassOverrideMode.Blackout();
              }
              MassOverrideRemote.Run(game, origin, !Equals(token, "nopos"), mode, left, seq, joining);
            }
          }
        }
      } else {
        if StrLen(lines[i]) > 0 {
          MassOverrideLog.Write("feed: a line not understood (" + ToString(ArraySize(f)) + " fields)");
        }
      }
      i += 1;
    }
    if next > poll.since {
      poll.since = next;
    }
  }
}

// One poller per game session, re-armed every Interval(). The delay system holding it is what keeps
// it alive while a request is out: RedHttpClient keeps only a WEAK reference to the callback's target
// and invokes it by name, and only a `cb` method (1.16.12: a one-shot callback died before its reply
// landed). A request still out is not doubled; one out longer than StuckSeconds() is given up.
public class MassOverrideFeedPoll extends DelayCallback {
  public let game: GameInstance;
  public let gen: Int32;
  public let since: Int32;      // -1 until the first answer of the session
  public let inFlight: Bool;
  public let sentAt: Float;
  public let polls: Int32;
  public let failures: Int32;

  public func Call() -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if IsDefined(prefs) && prefs.FeedGen() != this.gen {
      MassOverrideLog.Write("feed gen=" + ToString(this.gen) + " stops: gen=" + ToString(prefs.FeedGen()) + " took over");
      return;
    }
    GameInstance.GetDelaySystem(this.game).DelayCallback(this, MassOverrideFeed.Interval(), false);
    let now: Float = EngineTime.ToFloat(GameInstance.GetSimTime(this.game));
    if this.inFlight {
      if now - this.sentAt < MassOverrideFeed.StuckSeconds() { return; }
      MassOverrideLog.Write("feed: no answer in " + ToString(RoundF(now - this.sentAt)) + " s, asking again");
    }
    // in the menu, or while V loads: nothing to run a cast on yet
    let player: ref<PlayerPuppet> = GetPlayer(this.game);
    if !IsDefined(player) { return; }
    let session: String = "none";
    if IsDefined(prefs) {
      session = prefs.Session();
    }
    this.inFlight = true;
    this.sentAt = now;
    this.polls += 1;
    let callback: HttpCallback = HttpCallback.Create(this, n"OnReply");
    AsyncHttpClient.Get(callback, MassOverrideFeed.CastsUrl() + "?since=" + ToString(this.since) + "&session=" + session, []);
  }

  private cb func OnReply(response: ref<HttpResponse>) -> Void {
    this.inFlight = false;
    let status: Int32 = -1;
    if IsDefined(response) {
      status = response.GetStatusCode();
    }
    if status != 200 {
      this.failures += 1;
      // the first one, then one line every thirty (about a minute)
      let rounds: Int32 = this.failures / 30;
      if this.failures == 1 || this.failures - rounds * 30 == 0 {
        MassOverrideLog.Write("feed: the gate did not answer (status " + ToString(status) + "), " + ToString(this.failures) + " time(s) in a row");
      }
      return;
    }
    if this.failures > 0 {
      MassOverrideLog.Write("feed: the gate answers again after " + ToString(this.failures) + " failed poll(s)");
      this.failures = 0;
    }
    if this.since < 0 {
      MassOverrideLog.Write("feed: the gate's first answer (poll " + ToString(this.polls) + ")");
    }
    MassOverrideFeed.Handle(this.game, response.GetText(), this);
  }
}

// ANOTHER PLAYER'S CAST, run here: what the caster's own game does, from where the caster stood,
// for the time it has left -- without the RAM, the recharge, the gate, or anybody turned on this V.
public class MassOverrideRemote {
  public static func Cap() -> Int32 { return 1000; }

  public static func Run(game: GameInstance, origin: Vector4, placed: Bool, mode: Int32, seconds: Float, seq: Int32, joining: Bool) -> Void {
    let player: ref<PlayerPuppet> = GetPlayer(game);
    if !IsDefined(player) {
      MassOverrideLog.Write("remote seq=" + ToString(seq) + ": no V here yet, not run");
      return;
    }
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    let away: Float = -1.0;
    if placed {
      away = Vector4.Distance(player.GetWorldPosition(), origin);
    }
    let street: Bool = placed && away <= MassOverrideFeed.StreetReach();
    if !street && !MassOverrideFeed.CityWide() {
      MassOverrideLog.Write("remote seq=" + ToString(seq) + ": " + ToString(RoundF(away)) + " m away, not shown here");
      return;
    }
    let blackout: Bool = mode == MassOverrideMode.Blackout();
    MassOverrideRevert.EndActive(game, "another player's cast seq=" + ToString(seq));
    let n: Int32 = 0;
    let session: String = "none";
    if IsDefined(prefs) {
      n = prefs.CountRemote();
      session = prefs.Session();
    }
    let stats: ref<MassOverrideStats> = new MassOverrideStats();
    stats.nearestCut = -1.0;
    stats.nearestHack = -1.0;
    let run: ref<MassOverrideRun> = MassOverrideRun.Start(game, seconds);
    run.remote = true;
    run.seq = seq;
    run.farOff = !street;
    let targets: array<ref<MassOverrideTarget>>;
    if street {
      targets = MassOverrideRemote.Collect(player, origin, away, stats);
      MassOverrideApply.Targets(game, player, targets, run, stats, blackout, false);
      // the crowd around this V panics the way the caster's does
      stats.terror += MassOverridePeople.Panic(player);
    }
    stats.cityBefore = MassOverrideCity.StateName(game);
    if blackout {
      stats.cityForced = MassOverrideCity.Dark(game);
    } else {
      stats.cityForced = MassOverrideCity.Lit(game);
    }
    let inkLine: String = MassOverrideInk.Collect(run, stats);
    MassOverrideInk.Beat(run, !blackout, 1.0, 0);
    MassOverrideLights.Beat(run, !blackout, 1.0, 0);
    if street {
      MassOverrideFx.Burst(game, player, 1.5);
    }
    if blackout {
      let hold: ref<MassOverrideHold> = new MassOverrideHold();
      hold.game = game;
      hold.player = player;
      hold.targets = targets;
      hold.run = run;
      hold.tick = 1;
      GameInstance.GetDelaySystem(game).DelayCallback(hold, MassOverrideHold.Interval(), false);
    } else {
      let pulse: ref<MassOverridePulse> = new MassOverridePulse();
      pulse.game = game;
      pulse.player = player;
      pulse.targets = targets;
      pulse.run = run;
      pulse.tick = 1;
      pulse.lit = false;
      GameInstance.GetDelaySystem(game).DelayCallback(pulse, MassOverridePulse.Interval(), false);
    }
    let revert: ref<MassOverrideRevert> = new MassOverrideRevert();
    revert.game = game;
    revert.player = player;
    revert.targets = targets;
    revert.playerId = session;
    revert.run = run;
    revert.remote = true;
    revert.seq = seq;
    MassOverrideRevert.Arm(game, revert, seconds);
    let line: String = "remote seq=" + ToString(seq) + " (#" + ToString(n) + " here) mode=" + (blackout ? "blackout" : "blink")
      + " away=" + (placed ? ToString(RoundF(away)) + "m" : "unknown") + " street=" + (street ? "yes" : "no")
      + " left=" + ToString(RoundF(seconds)) + "s joining=" + (joining ? "yes" : "no")
      + " targets=" + ToString(ArraySize(targets)) + " glitched=" + ToString(stats.glitched) + " strobed=" + ToString(stats.strobed)
      + " cars=" + ToString(stats.accelerated + stats.alarms + stats.honks) + " ink=" + ToString(ArraySize(run.ink))
      + " lights=" + ToString(ArraySize(run.lights)) + " city=" + stats.cityBefore + (blackout ? "->forcedOff" : "->forcedOn")
      + " registry=" + ToString(stats.registry) + "/" + ToString(stats.registryNear);
    MassOverrideLog.Write(line);
    FTLog("[MassOverride] " + inkLine);
    MassOverrideCastPost.Report(game, "{\"phase\":\"remote\",\"playerId\":" + MassOverrideLog.Quote(session)
      + ",\"build\":\"" + MassOverrideBuild.Version() + "\""
      + ",\"seq\":" + ToString(seq)
      + ",\"mode\":\"" + (blackout ? "blackout" : "blink") + "\""
      + ",\"away\":" + ToString(RoundF(away))
      + ",\"street\":" + (street ? "true" : "false")
      + ",\"joining\":" + (joining ? "true" : "false")
      + ",\"seconds\":" + ToString(RoundF(seconds))
      + ",\"targets\":" + ToString(ArraySize(targets))
      + ",\"glitched\":" + ToString(stats.glitched)
      + ",\"emp\":" + ToString(stats.emp)
      + ",\"strobed\":" + ToString(stats.strobed)
      + ",\"accelerated\":" + ToString(stats.accelerated)
      + ",\"alarms\":" + ToString(stats.alarms)
      + ",\"honks\":" + ToString(stats.honks)
      + ",\"terror\":" + ToString(stats.terror)
      + ",\"inkTargets\":" + ToString(ArraySize(run.ink))
      + ",\"lightComponents\":" + ToString(ArraySize(run.lights))
      + ",\"city\":\"" + stats.cityBefore + "\""
      + ",\"cityForced\":" + (stats.cityForced ? "true" : "false")
      + ",\"registry\":" + ToString(stats.registry)
      + ",\"registryNear\":" + ToString(stats.registryNear)
      + ",\"hackInView\":" + ToString(stats.hackInView) + "}");
    MassOverrideLog.Flush(game, session, "remote");
  }

  // What the caster's sweep reaches around the cast: the devices streamed in near it (the attach
  // registry), and -- standing in it -- the caster's own first probe from here. Never people: nobody
  // is turned on this V; the crowd panics from the broadcast alone.
  public static func Collect(player: ref<PlayerPuppet>, origin: Vector4, away: Float, stats: ref<MassOverrideStats>) -> array<ref<MassOverrideTarget>> {
    let game: GameInstance = player.GetGame();
    let out: array<ref<MassOverrideTarget>>;
    let registry: ref<MassOverrideRegistry> = MassOverrideRegistry.Get(game);
    if IsDefined(registry) {
      stats.registry = registry.Size();
      stats.attachEvents = registry.AttachEvents();
      let ids: array<EntityID> = registry.Near(game, origin, MassOverrideRegistry.Reach());
      let i: Int32 = 0;
      while i < ArraySize(ids) && ArraySize(out) < MassOverrideRemote.Cap() {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, ids[i]) as GameObject;
        if IsDefined(object) {
          ArrayPush(out, MassOverrideProbe.DeviceTarget(object, stats));
          stats.registryNear += 1;
        }
        i += 1;
      }
    } else {
      stats.registry = -1;
    }
    if away >= 0.0 && away <= MassOverrideProbe.FirstReach() {
      let probed: array<ref<MassOverrideTarget>> = MassOverrideProbe.Fill(player, MassOverrideRemote.Cap(), true, stats);
      let j: Int32 = 0;
      while j < ArraySize(probed) && ArraySize(out) < MassOverrideRemote.Cap() {
        if probed[j].kind != MassOverrideKind.Person() && !MassOverrideProbe.Has(out, probed[j].entityId) {
          ArrayPush(out, probed[j]);
        }
        j += 1;
      }
    }
    return out;
  }
}

// What a cast does to what it found -- the same for the caster's own game (Capri.MassOverride.reds)
// and for another player's cast run here; people (turned on V, scared by name) only for the caster.
public class MassOverrideApply {
  public static func Targets(game: GameInstance, player: ref<PlayerPuppet>, targets: array<ref<MassOverrideTarget>>,
      run: ref<MassOverrideRun>, stats: ref<MassOverrideStats>, blackout: Bool, people: Bool) -> Void {
    let camera: ref<CameraSystem> = GameInstance.GetCameraSystem(game);
    let here: Vector4 = player.GetWorldPosition();
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      let object: ref<GameObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as GameObject;
      if targets[i].kind == MassOverrideKind.Person() {
        if people {
          // People turn on V in both modes, and each is scared by name, so
          // someone out of the broadcast's line still runs.
          MassOverrideEffects.SetHostile(object as NPCPuppet, player, true);
          stats.hostile += 1;
          if MassOverridePeople.Scare(player, object as NPCPuppet) {
            stats.terror += 1;
          }
          // Only ambient crowd runs from a panic; other players' puppets and
          // server-managed NPCs do not, which is what the count tells apart.
          let puppet: ref<ScriptedPuppet> = object as ScriptedPuppet;
          if IsDefined(puppet) && puppet.IsCrowd() {
            stats.crowd += 1;
          }
        }
      } else {
        if targets[i].kind == MassOverrideKind.Vehicle() {
          // A car with crowd at the wheel floors it, alarm going; a parked one's
          // alarm goes off; one someone else is in honks.
          let car: Int32 = MassOverrideCars.Hack(game, object as VehicleObject, targets[i]);
          if car == MassOverrideCars.Accelerate() {
            stats.accelerated += 1;
          }
          if car == MassOverrideCars.Alarm() {
            stats.alarms += 1;
          }
          if car == MassOverrideCars.Honk() {
            stats.honks += 1;
          }
          if car != MassOverrideCars.None() {
            stats.changed += 1;
            MassOverrideHack.Seen(stats, camera, object, here);
          }
        } else {
          // Machines and screens glitch the way V's own hack makes them, with the
          // EMP's sparks; lights go on the beat; doors, loot and terminals are
          // reported and left alone.
          let hit: Bool = false;
          if MassOverrideHack.Glitchable(object) {
            if MassOverrideHack.Glitch(targets[i], object) {
              stats.glitched += 1;
              stats.lightComponents += MassOverrideLights.Collect(run, object);
              hit = true;
            }
            if MassOverrideHack.Emp(targets[i], object, MassOverrideRun.Seconds(run, game)) {
              stats.emp += 1;
            }
          } else {
            if MassOverrideHack.Strobable(object) {
              if MassOverrideHack.StrobeStart(targets[i], object, !blackout) {
                stats.strobed += 1;
                stats.lightComponents += MassOverrideLights.Collect(run, object);
                if targets[i].stateOn {
                  stats.strobeLitBefore += 1;
                }
                hit = true;
              }
            } else {
              stats.notHacked += 1;
            }
          }
          if hit {
            stats.changed += 1;
            MassOverrideHack.Seen(stats, camera, object, here);
          }
        }
      }
      i += 1;
    }
  }
}

// Sends one cast to the gate (MassOverrideFeed.Base). The gate keeps the cooldown per game session
// and hands the cast to every other game (GET /casts); on a refusal it replies 409 and the cast is
// not handed out. The local cast keeps running on its own, so an unreachable server never blocks V.
public class MassOverrideCastPost extends DelayCallback {
  public let game: GameInstance;
  public let body: String;
  public let url: String;
  // True for the /players register: its reply only chains the cast, it never applies a mode.
  public let isRegister: Bool;
  public let isReport: Bool; // a diagnostics post: its reply applies nothing
  public let castBody: String;
  public let send: ref<MassOverrideCastSend>; // a try of this cast (MassOverrideCastSend), else none
  public let attempt: Int32;
  private let keepAlive: Bool; // the object kept itself scheduled for its reply

  // The JSON body for /cast: the caster's ids (V's entity id, the same on every PC, and this game's
  // own session id), where V stands, the mode this game runs, the cast's token, and the candidates as
  // { id, type }. The type is the kind name only; the server does not decide targets from it.
  public static func Body(player: ref<PlayerPuppet>, targets: array<ref<MassOverrideTarget>>, mode: String, token: String) -> String {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    let session: String = "";
    if IsDefined(prefs) {
      session = prefs.Session();
    }
    let at: Vector4 = player.GetWorldPosition();
    let body: String = "{\"playerId\":\"" + EntityID.ToDebugString(player.GetEntityID()) + "\""
      + ",\"session\":\"" + session + "\",\"token\":\"" + token + "\",\"mode\":\"" + mode + "\""
      + ",\"x\":" + ToString(at.X) + ",\"y\":" + ToString(at.Y) + ",\"z\":" + ToString(at.Z)
      + ",\"candidates\":[";
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      let kind: String = "person";
      if targets[i].kind == 1 { kind = "screen"; }
      if targets[i].kind == 2 { kind = "light"; }
      if targets[i].kind == 3 { kind = "vehicle"; }
      if i > 0 { body += ","; }
      body += "{\"id\":\"" + EntityID.ToDebugString(targets[i].entityId) + "\",\"type\":\"" + kind + "\"}";
      i += 1;
    }
    return body + "]}";
  }

  // How long this post keeps itself alive so its reply can be delivered. The answer
  // normally lands in well under a second; this only has to outlive the request.
  public static func KeepAliveSeconds() -> Float { return 60.0; }

  public func Call() -> Void {
    if this.keepAlive {
      // The keep-alive firing itself: nothing left to do, and no re-arm, so the
      // object is released now that its reply has already been handled.
      return;
    }
    this.keepAlive = true;
    // Hold a strong reference for the life of the request; see MassOverrideFeedPoll.
    GameInstance.GetDelaySystem(this.game).DelayCallback(this, MassOverrideCastPost.KeepAliveSeconds(), false);
    let callback: HttpCallback = HttpCallback.Create(this, n"OnReply");
    AsyncHttpClient.Post(callback, this.url, this.body, []);
  }

  // Registers the caster with the gate before the first cast. The server rejects a cast
  // from an unknown player, so this runs first and the cast follows its reply.
  public static func Register(game: GameInstance, playerId: String, castBody: String) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    let session: String = "";
    if IsDefined(prefs) {
      session = prefs.Session();
    }
    let body: String = "{\"id\":\"" + playerId + "\",\"session\":\"" + session + "\",\"ownsCapri\":true,\"capriSummoned\":true,\"balance\":100}";
    let post: ref<MassOverrideCastPost> = new MassOverrideCastPost();
    post.game = game;
    post.body = body;
    post.url = MassOverrideFeed.Base() + "/players";
    post.isRegister = true;
    post.castBody = castBody;
    GameInstance.GetDelaySystem(game).DelayCallback(post, 0.0, false);
  }

  // The numbers a cast actually produced, sent to the gate so they can be read on the
  // server. r6/storages can refuse a write from a script the storage does not know, so
  // the file log is not enough on its own; this path is known to work.
  public static func Report(game: GameInstance, body: String) -> Void {
    let post: ref<MassOverrideCastPost> = new MassOverrideCastPost();
    post.game = game;
    post.body = body;
    post.url = MassOverrideFeed.Base() + "/report";
    post.isRegister = false;
    post.isReport = true;
    GameInstance.GetDelaySystem(game).DelayCallback(post, 0.0, false);
  }

  // Sends the cast after the register's reply, so the server already knows the player.
  private func SendCast(game: GameInstance, castBody: String) -> Void {
    let post: ref<MassOverrideCastPost> = new MassOverrideCastPost();
    post.game = game;
    post.body = castBody;
    post.url = MassOverrideFeed.Base() + "/cast";
    post.isRegister = false;
    GameInstance.GetDelaySystem(game).DelayCallback(post, 0.0, false);
  }

  // `cb` and the keep-alive above are both required for RedHttpClient to deliver
  // this: a callback method is invoked by name, and only while its target is alive.
  private cb func OnReply(response: ref<HttpResponse>) -> Void {
    let ok: Bool = IsDefined(response) && response.GetStatusCode() == 200;
    if this.isReport { return; }
    if IsDefined(this.send) {
      this.send.Answered(this.attempt, response, this.isRegister);
      return;
    }
    if this.isRegister {
      MassOverrideLog.Write("register " + (ok ? "ok" : "failed") + " -> " + (ok ? "sending cast" : "cast not sent"));
      if ok {
        this.SendCast(this.game, this.castBody);
      }
      return;
    }
    if ok {
      // the gate hands it to every other game now (GET /casts); this game already runs it
      MassOverrideLog.Write("server cast ok: handed to every other game in the session");
    } else {
      let status: Int32 = IsDefined(response) ? response.GetStatusCode() : -1;
      let why: String = IsDefined(response) ? response.GetText() : "no response";
      MassOverrideLog.Write("server cast refused status=" + ToString(status) + " " + why);
    }
  }
}

// A CAST HANDED TO THE GATE, sent again until the gate has it. On 2026-11-12 a cast from a PC whose
// connection to the server dropped now and then ("Recv failure: Connection was reset", "Failed to
// connect ... after 21025 ms") ran on that PC only: the one request that carried it was lost, and
// no other game ever heard of it. Now the cast goes straight to /cast (the gate registers a game it
// does not know itself) and is sent again while no answer has come -- a try still out is not waited
// for: the gate answers a cast it already has (the same token) with that cast, so it is never run
// or charged twice. A refusal (409: recharging...) is an answer too. Each try and the outcome are in
// the cast's log lines, which go to the gate with its reports.
public class MassOverrideCastSend extends DelayCallback {
  public let game: GameInstance;
  public let body: String;
  public let token: String;
  public let attempts: Int32;
  public let answered: Bool;
  public let startedAt: Float;
  public let registered: Bool;

  public static func MaxAttempts() -> Int32 { return 6; }
  // A cast older than this is not sent any more: the others would only see its last seconds.
  public static func GiveUpSeconds() -> Float { return 26.0; }
  // Seconds from one try to the next while no answer has come.
  public static func Wait(attempt: Int32) -> Float {
    if attempt <= 1 { return 3.0; }
    if attempt == 2 { return 4.0; }
    return 5.0;
  }

  public static func Start(game: GameInstance, body: String, token: String) -> Void {
    let send: ref<MassOverrideCastSend> = new MassOverrideCastSend();
    send.game = game;
    send.body = body;
    send.token = token;
    send.startedAt = EngineTime.ToFloat(GameInstance.GetSimTime(game));
    GameInstance.GetDelaySystem(game).DelayCallback(send, 0.0, false);
  }

  // One try, or the check after one: nothing once the gate has answered.
  public func Call() -> Void {
    if this.answered { return; }
    let took: Float = EngineTime.ToFloat(GameInstance.GetSimTime(this.game)) - this.startedAt;
    if this.attempts >= MassOverrideCastSend.MaxAttempts() || took > MassOverrideCastSend.GiveUpSeconds() {
      MassOverrideLog.Write("server cast NOT delivered after " + ToString(this.attempts) + " tries in "
        + ToString(RoundF(took)) + " s (token " + this.token + "): it ran on this screen only");
      return;
    }
    this.attempts += 1;
    // the delay system holds this object (and the state the tries' replies write to) until the next check
    GameInstance.GetDelaySystem(this.game).DelayCallback(this, MassOverrideCastSend.Wait(this.attempts), false);
    if this.attempts > 1 {
      MassOverrideLog.Write("server cast: no answer yet, try " + ToString(this.attempts) + " at "
        + ToString(RoundF(took)) + " s (token " + this.token + ")");
    }
    this.Post(MassOverrideFeed.Base() + "/cast", this.body, false);
  }

  private func Post(url: String, body: String, register: Bool) -> Void {
    let post: ref<MassOverrideCastPost> = new MassOverrideCastPost();
    post.game = this.game;
    post.body = body;
    post.url = url;
    post.isRegister = register;
    post.send = this;
    post.attempt = this.attempts;
    GameInstance.GetDelaySystem(this.game).DelayCallback(post, 0.0, false);
  }

  // A try's answer. 200: the gate has it (sent once more, it answers with the cast it has). 409: refused, said.
  // 404: an older gate that wants the game registered first -- registered here, the next try follows.
  public func Answered(attempt: Int32, response: ref<HttpResponse>, register: Bool) -> Void {
    let status: Int32 = IsDefined(response) ? response.GetStatusCode() : -1;
    if register {
      MassOverrideLog.Write("server cast: registered with an older gate (status " + ToString(status) + ")");
      this.registered = status == 200;
      return;
    }
    if this.answered { return; }
    let took: Float = EngineTime.ToFloat(GameInstance.GetSimTime(this.game)) - this.startedAt;
    if status == 200 {
      this.answered = true;
      MassOverrideLog.Write("server cast ok on try " + ToString(attempt) + " of " + ToString(this.attempts) + " ("
        + ToString(RoundF(took)) + " s): handed to every other game in the session");
      return;
    }
    if status == 409 {
      this.answered = true;
      MassOverrideLog.Write("server cast refused on try " + ToString(attempt) + ": " + response.GetText());
      return;
    }
    if status == 404 && !this.registered {
      let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
      let session: String = IsDefined(prefs) ? prefs.Session() : "";
      this.Post(MassOverrideFeed.Base() + "/players", "{\"id\":\"" + session + "\",\"session\":\"" + session
        + "\",\"ownsCapri\":true,\"capriSummoned\":true,\"balance\":100}", true);
      return;
    }
    let why: String = IsDefined(response) ? response.GetText() : "no response";
    MassOverrideLog.Write("server cast try " + ToString(attempt) + " failed (status " + ToString(status) + " after "
      + ToString(RoundF(took)) + " s): " + why);
  }
}

// Registration check for the two services above, so a service that never
// registered is stated in the log instead of being inferred from a mode that never
// changes or a cache that never hits. Each lookup uses the same two spellings as the
// service's own Get(), and names the one that answered.
public class MassOverrideDiag {
  public static func CacheService() -> String {
    let container: ScriptableServiceContainer = GameInstance.GetScriptableServiceContainer();
    if IsDefined(container.GetService(n"MassOverrideCache") as MassOverrideCache) {
      return "cache=MassOverrideCache";
    }
    if IsDefined(container.GetService(n"Open77.MassOverrideCache") as MassOverrideCache) {
      return "cache=Open77.MassOverrideCache";
    }
    return "cache=none";
  }

  public static func PrefsService() -> String {
    let container: ScriptableServiceContainer = GameInstance.GetScriptableServiceContainer();
    if IsDefined(container.GetService(n"MassOverridePrefs") as MassOverridePrefs) {
      return "prefs=MassOverridePrefs";
    }
    if IsDefined(container.GetService(n"Open77.MassOverridePrefs") as MassOverridePrefs) {
      return "prefs=Open77.MassOverridePrefs";
    }
    return "prefs=none";
  }

  public static func Describe() -> String {
    return MassOverrideDiag.CacheService() + " " + MassOverrideDiag.PrefsService();
  }

  public static func AllPresent() -> Bool {
    let cache: String = MassOverrideDiag.CacheService();
    let prefs: String = MassOverrideDiag.PrefsService();
    return !Equals(cache, "cache=none") && !Equals(prefs, "prefs=none");
  }

  // How long the no-service fallback waits between warnings. An hour of sim time, so
  // a session sees it a couple of times at most rather than on every cast.
  public static func WarnWindowSeconds() -> Int32 { return 3600; }

  // True only the first time a missing service is reported. Whichever service did
  // register keeps the flag; if neither exists there is nowhere to remember it, so
  // the warning is limited to the first second of each warn window instead of
  // printing per cast. Either way the line stays visible and the log stays readable.
  public static func ShouldWarn(game: GameInstance) -> Bool {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if IsDefined(prefs) {
      if prefs.WarnedMissing() { return false; }
      prefs.MarkWarnedMissing();
      return true;
    }
    let cache: ref<MassOverrideCache> = MassOverrideCache.Get();
    if IsDefined(cache) {
      if cache.WarnedMissing() { return false; }
      cache.MarkWarnedMissing();
      return true;
    }
    return MassOverrideDiag.InWarnWindow(game);
  }

  private static func InWarnWindow(game: GameInstance) -> Bool {
    let now: Float = EngineTime.ToFloat(GameInstance.GetSimTime(game));
    let seconds: Int32 = Cast<Int32>(now);
    let block: Int32 = seconds / MassOverrideDiag.WarnWindowSeconds();
    return seconds - block * MassOverrideDiag.WarnWindowSeconds() < 1;
  }
}

// What one cast actually did, for the log. The counters are the measurement: a
// fill runs inside one frame, so sim time generally does not advance within it and
// `seconds` is the whole cast measured outside, which can honestly read 0.
public class MassOverrideStats {
  public let probes: Int32;   // targeting queries actually issued
  public let parts: Int32;    // target parts returned by those queries
  public let people: Int32;   // npcs added
  public let devices: Int32;  // screens, lights and vehicles added
  public let screens: Int32;  // of those, world widgets
  public let lights: Int32;   // of those, light components that are not vehicles
  public let vehicles: Int32; // of those, cars
  public let lightStates: Int32;    // lights whose own on/off (ToggleLight) changed
  public let lightFallbacks: Int32; // lights only the component switch could change
  public let lightEvents: Int32;    // entities a ToggleLightEvent was queued to
  public let changed: Int32;  // devices cut and cars set off by the cast itself
  public let cacheHit: Bool;  // the block's devices came from the cache
  public let hostile: Int32;  // people whose attitude towards V was set
  public let blocks: Int32;   // areas the cache holds
  public let seconds: Float;  // wall of the whole cast, as the engine reports it
  public let powerCut: Int32;     // devices sent SetDeviceUnpowered through their controller
  public let powerSkipped: Int32; // devices found but not on the power list (doors, loot, ...)
  public let alarms: Int32;       // parked cars whose alarm was switched on
  public let honks: Int32;        // occupied cars that were made to honk instead
  public let terror: Int32;       // panic stims sent: the broadcast from V plus one per person
  public let registry: Int32;     // devices the attach registry held at cast time (-1: none)
  public let registryNear: Int32; // of those, near V and not already found by the probe
  public let attachEvents: Int32; // device attach events the registry has seen this session
  public let cityBefore: String;  // city light state before the cast: default/forcedOn/forcedOff/missing
  public let cityForced: Bool;    // the ForcedOFF request was queued
  public let cityFuses: Int32;    // fuses the city light system drives (-1: no system)
  public let cityLights: Int32;   // lights behind those fuses
  public let hour: Int32;         // in-game hour: city lights are already off by day
  public let classes: String;     // devices found per class, "VendingMachine:25,TrafficLight:8"
  public let litBefore: Int32;    // of the devices cut, those that had a screen or a light on
  public let cutInView: Int32;    // of the devices cut, those inside the camera's frustum
  public let nearestCut: Float;   // metres from V to the nearest device cut (-1: none)
  public let crowd: Int32;        // of the people found, ambient crowd (the ones who can run)
  public let area: String;        // district:cell the cast was made in
  // 1.16.14 levers (MassOverrideHack, MassOverrideCars)
  public let glitched: Int32;     // machines and screens sent their own glitch
  public let emp: Int32;          // devices given the EMP sparks
  public let strobed: Int32;      // lights switched on the beat
  public let strobeLitBefore: Int32; // of those, the ones that were ON at the cast
  public let accelerated: Int32;  // crowd-driven cars given the Accelerate quickhack
  public let notHacked: Int32;    // devices no lever applies to (doors, loot, terminals...)
  public let hackInView: Int32;   // hacked devices and cars inside the camera's frustum
  public let nearestHack: Float;  // metres from V to the nearest hacked thing (-1: none)
  // 1.16.15 (MassOverrideInk, MassOverrideLights)
  public let inkLayers: Int32;       // world ink layers whose root goes on the beat
  public let worldWidgets: Int32;    // world widgets (wall and machine screens) on the beat
  public let inkNames: String;       // every ink layer by name, the ones taken marked *
  public let lightComponents: Int32; // light components on hacked devices that pulse
}

// The area a target is in. There is no coordinate-to-district lookup on 2.31 --
// district membership is authored as baked trigger volumes and the engine will
// only name the district the player is standing in (Open77Districts.reds records
// the compiler-probed results). So "area" is the player's district plus a 50 m
// world cell, which is what a flood is bucketed into.
public class MassOverrideArea {
  public static func CellSize() -> Float { return 50.0; }

  public static func Cell(position: Vector4) -> String {
    let x: Int32 = RoundF(position.X / MassOverrideArea.CellSize());
    let y: Int32 = RoundF(position.Y / MassOverrideArea.CellSize());
    return ToString(x) + ":" + ToString(y);
  }

  public static func Name(game: GameInstance, position: Vector4) -> String {
    return MassOverrideArea.District(game) + ":" + MassOverrideArea.Cell(position);
  }

  private static func District(game: GameInstance) -> String {
    let prevention: ref<PreventionSystem> =
      GameInstance.GetScriptableSystemsContainer(game).Get(n"PreventionSystem") as PreventionSystem;
    if !IsDefined(prevention) { return ""; }
    let current: wref<District> = prevention.GetCurrentDistrict();
    if !IsDefined(current) { return ""; }
    let record: ref<District_Record> = current.GetDistrictRecord();
    if !IsDefined(record) { return ""; }
    return record.EnumName();
  }
}

// One probe result, kept so a later flood in the same block can reuse it.
public class MassOverrideCachedTarget {
  public let entityId: EntityID;
  public let kind: Int32;
  public let label: String;
  public let cell: String; // the cell it was in when it was probed
}

public class MassOverrideCachedArea {
  public let key: String;  // district:cell
  public let cell: String;
  public let targets: array<ref<MassOverrideCachedTarget>>;
}

// Probe results per area. Looked up the same way Capri's own storage service is
// (class name in the scriptable service container). If the container ever hands
// back null, Get() returns null and the sweep simply probes every time -- the
// cache is an optimisation, never a requirement.
public class MassOverrideCache extends ScriptableService {
  private let m_areas: array<ref<MassOverrideCachedArea>>;
  private let m_warnedMissing: Bool; // the one-time "service missing" line was printed

  // Blocks remembered at once. Eight covers a district's worth of fights without
  // holding every light in Night City.
  public static func MaxAreas() -> Int32 { return 8; }

  // Capri's and Codeware's services are registered module-qualified
  // (n"Capri.CapriStorage", n"Codeware.UI.CustomPopupManager"), and this file has
  // no module, so both spellings are tried rather than assumed. A null result
  // only means the sweep probes every time.
  public static func Get() -> ref<MassOverrideCache> {
    let service: ref<MassOverrideCache> =
      GameInstance.GetScriptableServiceContainer().GetService(n"MassOverrideCache") as MassOverrideCache;
    if IsDefined(service) { return service; }
    return GameInstance.GetScriptableServiceContainer().GetService(n"Open77.MassOverrideCache") as MassOverrideCache;
  }

  public func Known(key: String) -> Bool {
    let i: Int32 = 0;
    while i < ArraySize(this.m_areas) {
      if Equals(this.m_areas[i].key, key) { return true; }
      i += 1;
    }
    return false;
  }

  public func AreaCount() -> Int32 {
    return ArraySize(this.m_areas);
  }

  public func WarnedMissing() -> Bool { return this.m_warnedMissing; }
  public func MarkWarnedMissing() -> Void { this.m_warnedMissing = true; }

  public func Forget() -> Void {
    ArrayClear(this.m_areas);
  }

  // Devices only. A person cached here would be stale the moment they walked on.
  public func Remember(key: String, cell: String, targets: array<ref<MassOverrideTarget>>) -> Void {
    let area: ref<MassOverrideCachedArea> = new MassOverrideCachedArea();
    area.key = key;
    area.cell = cell;
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].kind != 0 {
        let cached: ref<MassOverrideCachedTarget> = new MassOverrideCachedTarget();
        cached.entityId = targets[i].entityId;
        cached.kind = targets[i].kind;
        cached.label = targets[i].label;
        cached.cell = targets[i].area;
        ArrayPush(area.targets, cached);
      }
      i += 1;
    }
    let found: Bool = false;
    let j: Int32 = 0;
    while j < ArraySize(this.m_areas) {
      if Equals(this.m_areas[j].key, key) {
        this.m_areas[j] = area;
        found = true;
      }
      j += 1;
    }
    if !found {
      if ArraySize(this.m_areas) >= MassOverrideCache.MaxAreas() {
        ArrayErase(this.m_areas, 0);
      }
      ArrayPush(this.m_areas, area);
    }
  }

  // Only what is still there: the entity must still exist, still be switchable,
  // and still be standing in the cell it was cached in. That last check is how a
  // car that drove off drops out instead of being darkened somewhere else.
  // Anything that fails is dropped from the entry as it is read.
  public func Recall(game: GameInstance, key: String, cell: String) -> array<ref<MassOverrideTarget>> {
    let out: array<ref<MassOverrideTarget>>;
    let i: Int32 = 0;
    while i < ArraySize(this.m_areas) {
      if Equals(this.m_areas[i].key, key) {
        let kept: array<ref<MassOverrideCachedTarget>>;
        let j: Int32 = 0;
        while j < ArraySize(this.m_areas[i].targets) {
          let cached: ref<MassOverrideCachedTarget> = this.m_areas[i].targets[j];
          let object: ref<GameObject> = GameInstance.FindEntityByID(game, cached.entityId) as GameObject;
          if IsDefined(object) && Equals(cell, cached.cell)
            && Equals(MassOverrideArea.Cell(object.GetWorldPosition()), cached.cell)
            && MassOverrideEffects.CanBlink(object) {
            let target: ref<MassOverrideTarget> = new MassOverrideTarget();
            target.entityId = cached.entityId;
            target.kind = cached.kind;
            target.label = cached.label;
            target.area = cached.cell;
            // Cached entries store the device, not its state: the state is read now,
            // when the entry is turned back into a target and before any switching.
            target.screenWasOn = MassOverrideEffects.ScreenOn(object);
            target.lightWasOn = MassOverrideEffects.LightOn(object);
            ArrayPush(out, target);
            ArrayPush(kept, cached);
          }
          j += 1;
        }
        this.m_areas[i].targets = kept;
      }
      i += 1;
    }
    return out;
  }
}

// Multi-probe sweep.
//
// One query from V only reaches 40 m, which cannot see the next street's lamps or
// the billboards on the far side of a building. So the sweep is a breadth-first
// fill: every screen, light and vehicle found becomes the next probe, and the
// fill walks outward along the devices themselves. That follows a street around a
// corner instead of reaching through walls, and it stops on a probe budget rather
// than on distance alone.
public class MassOverrideProbe {
  // Reach of one chained probe.
  public static func Reach() -> Float { return 25.0; }

  // Reach of the FIRST probe, from V: much wider than a chained one. A cast measured
  // on a live session found only 16 candidates -- vehicles and people, not one screen
  // or light -- because every probe started at 25 m and the fill only grows through
  // devices it has already found. The opening sweep has to be wide enough to reach the
  // street's lamps and billboards on its own.
  public static func FirstReach() -> Float { return 70.0; }

  // Probes per cast. Each is one targeting query that returns its whole
  // neighbourhood, so this bounds the work a cast can do.
  public static func MaxProbes() -> Int32 { return 128; }

  // Entry point. A block whose devices are already cached costs one query for the
  // people and nothing else.
  public static func Collect(player: ref<PlayerPuppet>, cap: Int32, stats: ref<MassOverrideStats>) -> array<ref<MassOverrideTarget>> {
    let game: GameInstance = player.GetGame();
    let position: Vector4 = player.GetWorldPosition();
    let key: String = MassOverrideArea.Name(game, position);
    let cell: String = MassOverrideArea.Cell(position);
    let cache: ref<MassOverrideCache> = MassOverrideCache.Get();
    if IsDefined(cache) {
      stats.blocks = cache.AreaCount();
    }
    if IsDefined(cache) && cache.Known(key) {
      stats.cacheHit = true;
      let out: array<ref<MassOverrideTarget>> = MassOverrideProbe.Fill(player, cap, false, stats);
      let devices: array<ref<MassOverrideTarget>> = cache.Recall(game, key, cell);
      let i: Int32 = 0;
      while i < ArraySize(devices) && ArraySize(out) < cap {
        if !MassOverrideProbe.Has(out, devices[i].entityId) {
          ArrayPush(out, devices[i]);
        }
        i += 1;
      }
      return MassOverrideProbe.WithRegistered(player, out, cap, stats);
    }
    let probed: array<ref<MassOverrideTarget>> = MassOverrideProbe.Fill(player, cap, true, stats);
    if IsDefined(cache) {
      cache.Remember(key, cell, probed);
      stats.blocks = cache.AreaCount();
    }
    return MassOverrideProbe.WithRegistered(player, probed, cap, stats);
  }

  // Adds the devices the attach registry holds near V that the probe did not find:
  // the TVs, billboards, signs and lamps no targeting query returns. They are not
  // cached per area, because the registry already is the current list.
  public static func WithRegistered(player: ref<PlayerPuppet>, targets: array<ref<MassOverrideTarget>>, cap: Int32, stats: ref<MassOverrideStats>) -> array<ref<MassOverrideTarget>> {
    let out: array<ref<MassOverrideTarget>> = targets;
    let game: GameInstance = player.GetGame();
    let registry: ref<MassOverrideRegistry> = MassOverrideRegistry.Get(game);
    if !IsDefined(registry) {
      stats.registry = -1;
      return out;
    }
    stats.registry = registry.Size();
    stats.attachEvents = registry.AttachEvents();
    let ids: array<EntityID> = registry.Near(game, player.GetWorldPosition(), MassOverrideRegistry.Reach());
    let i: Int32 = 0;
    while i < ArraySize(ids) && ArraySize(out) < cap {
      if !MassOverrideProbe.Has(out, ids[i]) {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, ids[i]) as GameObject;
        if IsDefined(object) {
          ArrayPush(out, MassOverrideProbe.DeviceTarget(object, stats));
          stats.registryNear += 1;
        }
      }
      i += 1;
    }
    return out;
  }

  // A device as a target, its state read now, before anything is switched.
  public static func DeviceTarget(device: ref<GameObject>, stats: ref<MassOverrideStats>) -> ref<MassOverrideTarget> {
    let target: ref<MassOverrideTarget> = new MassOverrideTarget();
    target.entityId = device.GetEntityID();
    target.kind = MassOverrideEffects.KindOf(device);
    target.screenWasOn = MassOverrideEffects.ScreenOn(device);
    target.lightWasOn = MassOverrideEffects.LightOn(device);
    target.label = NameToString(device.GetClassName());
    target.area = MassOverrideArea.Cell(device.GetWorldPosition());
    stats.devices += 1;
    if target.kind == MassOverrideKind.Vehicle() {
      stats.vehicles += 1;
    } else {
      if target.kind == MassOverrideKind.Screen() {
        stats.screens += 1;
      } else {
        stats.lights += 1;
      }
    }
    return target;
  }

  // Devices per class, for the report: "VendingMachine:25,TrafficLight:8". The counts
  // say what a cast actually had to work with, which the kind totals cannot.
  public static func Classes(targets: array<ref<MassOverrideTarget>>) -> String {
    let names: array<String>;
    let counts: array<Int32>;
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].kind != MassOverrideKind.Person() {
        let found: Int32 = -1;
        let j: Int32 = 0;
        while j < ArraySize(names) {
          if Equals(names[j], targets[i].label) { found = j; }
          j += 1;
        }
        if found < 0 {
          ArrayPush(names, targets[i].label);
          ArrayPush(counts, 1);
        } else {
          counts[found] = counts[found] + 1;
        }
      }
      i += 1;
    }
    let out: String = "";
    let k: Int32 = 0;
    while k < ArraySize(names) {
      if k > 0 { out += ","; }
      out += names[k] + ":" + ToString(counts[k]);
      k += 1;
    }
    return out;
  }

  public static func Has(targets: array<ref<MassOverrideTarget>>, id: EntityID) -> Bool {
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if Equals(targets[i].entityId, id) { return true; }
      i += 1;
    }
    return false;
  }

  // The fill. With includeDevices false it is a single probe from V for people,
  // because devices are what grow the frontier and those are already known.
  public static func Fill(player: ref<PlayerPuppet>, cap: Int32, includeDevices: Bool, stats: ref<MassOverrideStats>) -> array<ref<MassOverrideTarget>> {
    let out: array<ref<MassOverrideTarget>>;
    let seen: array<EntityID>;
    let frontier: array<EntityID>;
    ArrayPush(frontier, player.GetEntityID());
    let next: Int32 = 0;
    let probes: Int32 = 0;
    let playerId: EntityID = player.GetEntityID();
    while next < ArraySize(frontier) && probes < MassOverrideProbe.MaxProbes() && ArraySize(out) < cap {
      let anchorId: EntityID = frontier[next];
      let anchor: ref<GameObject> = GameInstance.FindEntityByID(player.GetGame(), anchorId) as GameObject;
      next += 1;
      probes += 1;
      stats.probes += 1;
      if IsDefined(anchor) {
        let query: TargetSearchQuery;
        query.testedSet = TargetingSet.Complete;
        query.searchFilter = TSF_Any(
          TSFMV.Obj_Puppet | TSFMV.Obj_Device | TSFMV.Obj_Other |
          TSFMV.Att_Friendly | TSFMV.Att_Hostile | TSFMV.Att_Neutral |
          TSFMV.St_Alive | TSFMV.St_TurnedOn | TSFMV.St_TurnedOff);
        query.maxDistance = Equals(anchorId, playerId)
          ? MassOverrideProbe.FirstReach() : MassOverrideProbe.Reach();
        query.filterObjectByDistance = true;
        query.includeSecondaryTargets = true;
        query.ignoreInstigator = true;
        let parts: array<TS_TargetPartInfo>;
        GameInstance.GetTargetingSystem(anchor.GetGame()).GetTargetParts(anchor, query, parts);
        stats.parts += ArraySize(parts);
        let i: Int32 = 0;
        while i < ArraySize(parts) && ArraySize(out) < cap {
          let comp: wref<TargetingComponent> = TS_TargetPartInfo.GetComponent(parts[i]);
          if IsDefined(comp) {
            let entity: wref<Entity> = comp.GetEntity();
            if IsDefined(entity) {
              let npc: ref<NPCPuppet> = entity as NPCPuppet;
              if IsDefined(npc) {
                if !ArrayContains(seen, npc.GetEntityID()) {
                  ArrayPush(seen, npc.GetEntityID());
                  let person: ref<MassOverrideTarget> = new MassOverrideTarget();
                  person.entityId = npc.GetEntityID();
                  person.kind = 0;
                  person.label = NameToString(npc.GetClassName());
                  person.area = MassOverrideArea.Cell(npc.GetWorldPosition());
                  stats.people += 1;
                  ArrayPush(out, person);
                  // People seed the fill too. Only devices used to grow the frontier,
                  // so a street with few devices stopped after one or two probes and a
                  // 70 m cast returned 34 entities: nothing to see.
                  if ArraySize(frontier) < MassOverrideProbe.MaxProbes() {
                    ArrayPush(frontier, npc.GetEntityID());
                  }
                }
              } else if includeDevices {
                let device: ref<GameObject> = entity as GameObject;
                if IsDefined(device) && !ArrayContains(seen, device.GetEntityID())
                  && MassOverrideEffects.CanBlink(device) {
                  ArrayPush(seen, device.GetEntityID());
                  let screen: ref<MassOverrideTarget> = new MassOverrideTarget();
                  screen.entityId = device.GetEntityID();
                  screen.kind = MassOverrideEffects.KindOf(device);
                  // Read before anything is switched: Collect runs before the apply
                  // pass, so this is the pre-cast state.
                  screen.screenWasOn = MassOverrideEffects.ScreenOn(device);
                  screen.lightWasOn = MassOverrideEffects.LightOn(device);
                  screen.label = NameToString(device.GetClassName());
                  screen.area = MassOverrideArea.Cell(device.GetWorldPosition());
                  stats.devices += 1;
                  if screen.kind == MassOverrideKind.Vehicle() {
                    stats.vehicles += 1;
                  } else if screen.kind == MassOverrideKind.Screen() {
                    stats.screens += 1;
                  } else {
                    stats.lights += 1;
                  }
                  ArrayPush(out, screen);
                  // The next probe: this is what makes the fill follow the street.
                  if ArraySize(frontier) < MassOverrideProbe.MaxProbes() {
                    ArrayPush(frontier, device.GetEntityID());
                  }
                }
              }
            }
          }
          i += 1;
        }
      }
    }
    return out;
  }
}

public class MassOverrideEffects {
  // Hostility on an NPC: the same attitude call Open77PlayerModels.reds uses.
  public static func SetHostile(npc: ref<NPCPuppet>, player: ref<PlayerPuppet>, on: Bool) -> Void {
    if !IsDefined(npc) || !IsDefined(player) { return; }
    let attitude: EAIAttitude = on ? EAIAttitude.AIA_Hostile : EAIAttitude.AIA_Neutral;
    npc.GetAttitudeAgent().SetAttitudeTowards(player.GetAttitudeAgent(), attitude);
  }

  // True when this entity has anything Mass Override can switch: a world widget
  // (billboard, TV, LCD screen, vending machine) or a light (street light, lamp,
  // traffic light, vehicle headlight).
  public static func CanBlink(target: ref<GameObject>) -> Bool {
    if !IsDefined(target) { return false; }
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      if MassOverrideEffects.IsBlinkable(components[i]) { return true; }
      i += 1;
    }
    return false;
  }

  // Switches every light and screen on this entity on or off. Returns how many
  // actually changed, so a revert is a no-op on anything that was already off.
  //
  // Screens keep using the component switch, because that is what the vanilla
  // screen classes do (lcdScreen TurnOffScreen -> m_uiComponent.Toggle(false)).
  // Lights use the light's own state, not the component: Toggle(false) only
  // disables the component, which a device's controller can turn straight back
  // on, whereas ToggleLight sets the light's own on/off. The vanilla billboard
  // does exactly this through ToggleLightEvent, so that event is queued too.
  public static func Blink(target: ref<GameObject>, on: Bool) -> Int32 {
    // Counts thrown away: the pulses, the hold and the revert only need the work
    // done. The cast itself uses BlinkReported so the log can attribute it.
    return MassOverrideEffects.BlinkReported(target, on, new MassOverrideStats());
  }

  // The same switch, reporting which path changed what.
  public static func BlinkReported(target: ref<GameObject>, on: Bool, stats: ref<MassOverrideStats>) -> Int32 {
    return MassOverrideEffects.Switch(target, on, on, stats);
  }

  // Both parts independently, which is what a revert needs: screens and lights each
  // go back to what they were, and either may be restored without the other.
  public static func Switch(target: ref<GameObject>, screenOn: Bool, lightOn: Bool, stats: ref<MassOverrideStats>) -> Int32 {
    if !IsDefined(target) { return 0; }
    let changed: Int32 = 0;
    let hasLight: Bool = false;
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      let widget: ref<IWorldWidgetComponent> = components[i] as IWorldWidgetComponent;
      if IsDefined(widget) {
        if widget.IsEnabled() != screenOn {
          widget.Toggle(screenOn);
          changed += 1;
        }
      } else {
        let light: ref<gameLightComponent> = components[i] as gameLightComponent;
        if IsDefined(light) {
          hasLight = true;
          let path: Int32 = MassOverrideEffects.SetLight(light, lightOn);
          if path != MassOverrideLightSwitch.None() {
            changed += 1;
          }
          if path == MassOverrideLightSwitch.State() || path == MassOverrideLightSwitch.Both() {
            stats.lightStates += 1;
          }
          if path == MassOverrideLightSwitch.Component() || path == MassOverrideLightSwitch.Both() {
            stats.lightFallbacks += 1;
          }
        }
      }
      i += 1;
    }
    // The same event billboard.script queues: evt.toggle = on; QueueEvent(evt).
    // Queued once per entity, after the per-component pass, so lights that sit on
    // a mesh or a child rather than on a component of their own follow too.
    if hasLight {
      let evt: ref<ToggleLightEvent> = new ToggleLightEvent();
      evt.toggle = lightOn;
      evt.loop = false;
      target.QueueEvent(evt);
      stats.lightEvents += 1;
    }
    return changed;
  }

  // gameLightComponent.ToggleLight(on, loop) and IsOn() are both in the 2.31 RTTI
  // table. State is compared first so a revert does not re-run a light that is
  // already where it should be, and so the hold can tell whether a device has
  // switched its light back on behind us.
  //
  // The component toggle is kept as the fallback: a light whose IsOn() never
  // changes (no light state to set, or a component that ignores ToggleLight) is
  // still hidden by disabling the component, which is how every screen is switched.
  // Both express the same desired state, so they cannot fight each other.
  private static func SetLight(light: ref<gameLightComponent>, on: Bool) -> Int32 {
    let path: Int32 = MassOverrideLightSwitch.None();
    if light.IsOn() != on {
      light.ToggleLight(on, false);
      path = MassOverrideLightSwitch.State();
    }
    if light.IsEnabled() != on {
      light.Toggle(on);
      if path == MassOverrideLightSwitch.State() {
        path = MassOverrideLightSwitch.Both();
      } else {
        path = MassOverrideLightSwitch.Component();
      }
    }
    return path;
  }

  // One swipe of the whole target list: dark or lit. Used by the blackout (once
  // dark, restored at revert) and by each pulse of the blink.
  public static func SetAll(game: GameInstance, targets: array<ref<MassOverrideTarget>>, lit: Bool) -> Void {
    // One sink for the whole swipe: the pulses and the hold do not report.
    let sink: ref<MassOverrideStats> = new MassOverrideStats();
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].kind != 0 {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as GameObject;
        MassOverrideEffects.BlinkReported(object, lit, sink);
      }
      i += 1;
    }
  }

  // Every device this cast cut, given its power back through its own controller,
  // which restores the state it cached and lets the device switch its own screens
  // and lights back on -- a traffic light comes back on red or green, not all three.
  // People and cars are the revert's.
  public static func RestoreAll(game: GameInstance, targets: array<ref<MassOverrideTarget>>) -> Void {
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      let target: ref<MassOverrideTarget> = targets[i];
      if target.cut {
        MassOverridePower.RestoreTarget(target, game);
      }
      i += 1;
    }
  }

  // One beat of the blink: every listed device loses its power or gets it back.
  public static func Beat(game: GameInstance, targets: array<ref<MassOverrideTarget>>, lit: Bool) -> Void {
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      let target: ref<MassOverrideTarget> = targets[i];
      if target.kind != MassOverrideKind.Person() && target.kind != MassOverrideKind.Vehicle() {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, target.entityId) as GameObject;
        if lit {
          if target.cut {
            MassOverridePower.RestoreTarget(target, game);
          }
        } else {
          if MassOverridePower.Allowed(object) {
            MassOverridePower.CutTarget(target, object);
          }
        }
      }
      i += 1;
    }
  }

  // The part of a blackout that does not hold itself: see MassOverridePower.NeedsHold.
  public static func HoldDark(game: GameInstance, targets: array<ref<MassOverrideTarget>>) -> Void {
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].cut {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as GameObject;
        if MassOverridePower.NeedsHold(object) {
          MassOverrideEffects.LightsOff(object);
        }
      }
      i += 1;
    }
  }

  // The device's own lights-off: the event trafficLight.script's TurnOffLights queues.
  // It switches the lights' state only, never the components, so the device can light
  // them again itself when its power comes back. (Disabling the components, as the
  // component pass does, would leave them dark even then.)
  public static func LightsOff(target: ref<GameObject>) -> Void {
    if !IsDefined(target) { return; }
    let evt: ref<ToggleLightEvent> = new ToggleLightEvent();
    evt.toggle = false;
    evt.loop = false;
    target.QueueEvent(evt);
  }

  // A screen is any world widget component. A light is a gameLightComponent,
  // which is what ElectricLight requests for a street light, a lamp or a traffic
  // light; vehicleLightComponent derives from it, so headlights match too.
  // Nothing else on the entity is touched, so collision, meshes and interaction
  // stay as they were.
  private static func IsBlinkable(component: ref<IComponent>) -> Bool {
    if !IsDefined(component) { return false; }
    if IsDefined(component as IWorldWidgetComponent) { return true; }
    return IsDefined(component as gameLightComponent);
  }

  // What kind of thing this is, for the log and the cache. Vehicles are tested
  // first: a car carries light components and sometimes dashboard widgets, so
  // testing screens first would file it as a screen and hide the one number that
  // says whether a probe reached any cars at all.
  public static func KindOf(target: ref<GameObject>) -> Int32 {
    if !IsDefined(target) { return MassOverrideKind.Screen(); }
    if IsDefined(target as VehicleObject) { return MassOverrideKind.Vehicle(); }
    if MassOverrideEffects.HasScreen(target) { return MassOverrideKind.Screen(); }
    return MassOverrideKind.Light();
  }

  public static func HasScreen(target: ref<GameObject>) -> Bool {
    if !IsDefined(target) { return false; }
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      if IsDefined(components[i]) && IsDefined(components[i] as IWorldWidgetComponent) {
        return true;
      }
      i += 1;
    }
    return false;
  }

  // Whether anything of that kind is currently on. Used to snapshot the state a
  // revert has to put back.
  public static func ScreenOn(target: ref<GameObject>) -> Bool {
    if !IsDefined(target) { return false; }
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      let widget: ref<IWorldWidgetComponent> = components[i] as IWorldWidgetComponent;
      if IsDefined(widget) && widget.IsEnabled() { return true; }
      i += 1;
    }
    return false;
  }

  public static func LightOn(target: ref<GameObject>) -> Bool {
    if !IsDefined(target) { return false; }
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      let light: ref<gameLightComponent> = components[i] as gameLightComponent;
      if IsDefined(light) && light.IsOn() { return true; }
      i += 1;
    }
    return false;
  }

  public static func HasLight(target: ref<GameObject>) -> Bool {
    if !IsDefined(target) { return false; }
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      if IsDefined(components[i]) && IsDefined(components[i] as gameLightComponent) {
        return true;
      }
      i += 1;
    }
    return false;
  }
}

// One cast's beat, shared by its pulses and its revert. The pulses are chained one
// delay after another, so over thirty seconds they drift by frames; a pulse that
// landed after the revert would switch a light the revert had just put back, or
// leave the city request standing. The revert marks the run ended, and no pulse
// switches anything after `endAt` either.
public class MassOverrideRun {
  public let ended: Bool;
  public let endAt: Float;
  public let remote: Bool;  // another player's cast, run here (MassOverrideRemote)
  public let farOff: Bool;  // that cast was beyond StreetReach(): the city's part only, no street, no panic
  public let seq: Int32;    // its seq at the gate
  public let ink: array<ref<MassOverrideInkTarget>>;      // billboards and screens (MassOverrideInk)
  public let lights: array<ref<MassOverrideLightTarget>>; // light components (MassOverrideLights)

  public static func Start(game: GameInstance, seconds: Float) -> ref<MassOverrideRun> {
    let run: ref<MassOverrideRun> = new MassOverrideRun();
    run.endAt = EngineTime.ToFloat(GameInstance.GetSimTime(game)) + seconds - 0.2;
    return run;
  }

  public func Live(game: GameInstance) -> Bool {
    if this.ended { return false; }
    return EngineTime.ToFloat(GameInstance.GetSimTime(game)) < this.endAt;
  }

  // Seconds the run has left (what the EMP sparks last); the cast's full length without a run.
  public static func Seconds(run: ref<MassOverrideRun>, game: GameInstance) -> Float {
    if !IsDefined(run) { return 30.0; }
    let left: Float = run.endAt + 0.2 - EngineTime.ToFloat(GameInstance.GetSimTime(game));
    if left < 1.0 { return 1.0; }
    return left;
  }
}

// BILLBOARDS AND SCREENS. An ink root on the beat: its own opacity and tint saved at the
// cast, then lit in the beat's colour or nearly gone, and put back at the revert.
public class MassOverrideInkTarget {
  public let widget: wref<inkWidget>;
  public let opacity: Float;
  public let tint: HDRColor;
  public let source: Int32; // 0 = a world ink layer's root, 1 = a world widget's root
}

public class MassOverrideInk {
  public static func Cap() -> Int32 { return 400; }

  // A layer drawn into the world -- advertisements, world UI, fluff -- not over the
  // screen: HUD, menus, notifications and loading screens are never touched.
  public static func WorldLayer(name: String) -> Bool {
    let lower: String = StrLower(name);
    if StrContains(lower, "hud") || StrContains(lower, "menu") || StrContains(lower, "notification")
        || StrContains(lower, "loading") || StrContains(lower, "photo") {
      return false;
    }
    return StrContains(lower, "advert") || StrContains(lower, "world") || StrContains(lower, "fluff");
  }

  public static func Add(run: ref<MassOverrideRun>, widget: ref<inkWidget>, source: Int32) -> Bool {
    if !IsDefined(run) || !IsDefined(widget) { return false; }
    if ArraySize(run.ink) >= MassOverrideInk.Cap() { return false; }
    let target: ref<MassOverrideInkTarget> = new MassOverrideInkTarget();
    target.widget = widget;
    target.opacity = widget.GetOpacity();
    target.tint = widget.GetTintColor();
    target.source = source;
    ArrayPush(run.ink, target);
    return true;
  }

  // Every world layer's root, then every world widget's root. Returns a line for the log
  // naming every layer, so a layer that should have been taken can be found by name.
  public static func Collect(run: ref<MassOverrideRun>, stats: ref<MassOverrideStats>) -> String {
    let ink: ref<inkSystem> = GameInstance.GetInkSystem();
    if !IsDefined(ink) { return "ink=missing"; }
    let names: String = "";
    let layers: array<ref<inkLayerWrapper>> = ink.GetLayers();
    let i: Int32 = 0;
    while i < ArraySize(layers) {
      let layer: ref<inkLayerWrapper> = layers[i];
      if IsDefined(layer) {
        let name: String = NameToString(layer.GetLayerName());
        let taken: Bool = false;
        if MassOverrideInk.WorldLayer(name) {
          let window: ref<inkWidget> = layer.GetVirtualWindow();
          taken = MassOverrideInk.Add(run, window, 0);
          if taken { stats.inkLayers += 1; }
        }
        if StrLen(names) > 0 { names += ","; }
        names += name;
        if taken { names += "*"; }
      }
      i += 1;
    }
    let widgets: array<wref<inkIGameController>> = ink.GetWorldWidgets();
    let w: Int32 = 0;
    while w < ArraySize(widgets) {
      let controller: ref<inkIGameController> = widgets[w];
      if IsDefined(controller) {
        let root: ref<inkWidget> = controller.GetRootWidget();
        if MassOverrideInk.Add(run, root, 1) { stats.worldWidgets += 1; }
      }
      w += 1;
    }
    stats.inkNames = names;
    return "layers=" + ToString(ArraySize(layers)) + " [" + names + "] worldWidgets=" + ToString(ArraySize(widgets));
  }

  // The hack's colours, one per beat: red, cyan, magenta, acid green. Division and
  // subtraction rather than a modulo, as elsewhere in these files.
  public static func Pick(tick: Int32) -> Int32 {
    let rounds: Int32 = tick / 4;
    return tick - rounds * 4;
  }

  public static func Colour(tick: Int32) -> HDRColor {
    let c: HDRColor;
    c.Alpha = 1.0;
    let pick: Int32 = MassOverrideInk.Pick(tick);
    if pick == 0 { c.Red = 1.0; c.Green = 0.05; c.Blue = 0.1; }
    if pick == 1 { c.Red = 0.0; c.Green = 1.0; c.Blue = 1.0; }
    if pick == 2 { c.Red = 1.0; c.Green = 0.0; c.Blue = 1.0; }
    if pick == 3 { c.Red = 0.35; c.Green = 1.0; c.Blue = 0.0; }
    return c;
  }

  // One beat. Lit: its own opacity, in the beat's colour. Dark: nearly gone. With
  // `chance` below 1.0 each root draws its own state (the blackout's flicker).
  public static func Beat(run: ref<MassOverrideRun>, on: Bool, chance: Float, tick: Int32) -> Int32 {
    if !IsDefined(run) { return 0; }
    let colour: HDRColor = MassOverrideInk.Colour(tick);
    let changed: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(run.ink) {
      let target: ref<MassOverrideInkTarget> = run.ink[i];
      let widget: ref<inkWidget> = target.widget;
      if IsDefined(widget) {
        let lit: Bool = on;
        if chance < 1.0 {
          lit = RandF() < chance;
        }
        if lit {
          widget.SetOpacity(target.opacity);
          widget.SetTintColor(colour);
        } else {
          widget.SetOpacity(target.opacity * 0.05);
        }
        changed += 1;
      }
      i += 1;
    }
    return changed;
  }

  public static func Restore(run: ref<MassOverrideRun>) -> Int32 {
    if !IsDefined(run) { return 0; }
    let restored: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(run.ink) {
      let target: ref<MassOverrideInkTarget> = run.ink[i];
      let widget: ref<inkWidget> = target.widget;
      if IsDefined(widget) {
        widget.SetOpacity(target.opacity);
        widget.SetTintColor(target.tint);
        restored += 1;
      }
      i += 1;
    }
    return restored;
  }
}

// LIGHTS, component by component. Every gameLightComponent on a hacked device is
// switched on the beat and recoloured with SetParameters -- what the game's own
// ChangeLightEvent ends in (gameLightComponent.script) -- at three times its intensity,
// so a lamp the timetable keeps off by day flashes red, cyan, magenta and green. A
// light's emissive surface follows its component (materialZone), so the lamp heads,
// signal heads and machine trims change, not only the light they cast.
public class MassOverrideLightTarget {
  public let light: wref<gameLightComponent>;
  public let settings: gameLightSettings;
  public let on: Bool;
}

public class MassOverrideLights {
  public static func Cap() -> Int32 { return 600; }
  public static func Boost() -> Float { return 3.0; }

  public static func Collect(run: ref<MassOverrideRun>, object: ref<GameObject>) -> Int32 {
    if !IsDefined(run) || !IsDefined(object) { return 0; }
    let added: Int32 = 0;
    let components: array<ref<IComponent>> = object.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) && ArraySize(run.lights) < MassOverrideLights.Cap() {
      let light: ref<gameLightComponent> = components[i] as gameLightComponent;
      if IsDefined(light) {
        let target: ref<MassOverrideLightTarget> = new MassOverrideLightTarget();
        target.light = light;
        target.settings = light.GetCurrentSettings();
        target.on = light.IsOn();
        ArrayPush(run.lights, target);
        added += 1;
      }
      i += 1;
    }
    return added;
  }

  public static func Colour(tick: Int32) -> Color {
    let c: Color;
    c.Alpha = Cast<Uint8>(255);
    let pick: Int32 = MassOverrideInk.Pick(tick);
    if pick == 0 { c.Red = Cast<Uint8>(255); c.Green = Cast<Uint8>(16); c.Blue = Cast<Uint8>(32); }
    if pick == 1 { c.Red = Cast<Uint8>(0); c.Green = Cast<Uint8>(255); c.Blue = Cast<Uint8>(255); }
    if pick == 2 { c.Red = Cast<Uint8>(255); c.Green = Cast<Uint8>(0); c.Blue = Cast<Uint8>(255); }
    if pick == 3 { c.Red = Cast<Uint8>(90); c.Green = Cast<Uint8>(255); c.Blue = Cast<Uint8>(0); }
    return c;
  }

  public static func Beat(run: ref<MassOverrideRun>, on: Bool, chance: Float, tick: Int32) -> Int32 {
    if !IsDefined(run) { return 0; }
    let colour: Color = MassOverrideLights.Colour(tick);
    let changed: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(run.lights) {
      let target: ref<MassOverrideLightTarget> = run.lights[i];
      let light: ref<gameLightComponent> = target.light;
      if IsDefined(light) {
        let lit: Bool = on;
        if chance < 1.0 {
          lit = RandF() < chance;
        }
        let settings: gameLightSettings = target.settings;
        if lit {
          settings.color = colour;
          settings.strength = 1.0;
          settings.intensity = target.settings.intensity * MassOverrideLights.Boost();
          light.ToggleLight(true);
        } else {
          settings.strength = 0.0;
        }
        light.SetParameters(settings, 0.05);
        if !lit {
          light.ToggleLight(false);
        }
        changed += 1;
      }
      i += 1;
    }
    return changed;
  }

  public static func Restore(run: ref<MassOverrideRun>) -> Int32 {
    if !IsDefined(run) { return 0; }
    let restored: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(run.lights) {
      let target: ref<MassOverrideLightTarget> = run.lights[i];
      let light: ref<gameLightComponent> = target.light;
      if IsDefined(light) {
        light.SetParameters(target.settings, 0.1);
        light.ToggleLight(target.on);
        restored += 1;
      }
      i += 1;
    }
    return restored;
  }
}

// V'S SCREEN. The glitch the game plays over V's view when a scene is fast-forwarded
// (player.script: transition_glitch_loop), started as the wave goes out and stopped by
// this callback a moment later.
public class MassOverrideFx extends DelayCallback {
  public let player: wref<PlayerPuppet>;

  public static func Name() -> CName { return n"transition_glitch_loop"; }

  public static func Burst(game: GameInstance, player: ref<PlayerPuppet>, seconds: Float) -> Bool {
    if !IsDefined(player) { return false; }
    GameObjectEffectHelper.StartEffectEvent(player, MassOverrideFx.Name(), false);
    let stop: ref<MassOverrideFx> = new MassOverrideFx();
    stop.player = player;
    GameInstance.GetDelaySystem(game).DelayCallback(stop, seconds, false);
    return true;
  }

  public func Call() -> Void {
    let player: ref<PlayerPuppet> = this.player;
    if IsDefined(player) {
      GameObjectEffectHelper.StopEffectEvent(player, MassOverrideFx.Name());
    }
  }
}

// Blink mode: every strobed light and the city's own lights flip together twice a
// second for the whole duration, while the machines and screens glitch. Each pulse
// arms the next on the delay system, so a dismissed Capri does not stop it. The panic
// and the cars' Accelerate hack are renewed every few seconds.
public class MassOverridePulse extends DelayCallback {
  public let game: GameInstance;
  public let player: wref<PlayerPuppet>;
  public let targets: array<ref<MassOverrideTarget>>;
  public let run: ref<MassOverrideRun>;
  public let tick: Int32;
  public let lit: Bool; // the state this pulse switches to

  // Twice a second. The switches go through the devices' own controllers, which take
  // a frame or two, and the city's lamps follow with their authored stagger; a faster
  // strobe blurs into a flicker nobody reads as a beat.
  public static func Interval() -> Float { return 0.5; }

  public func Call() -> Void {
    if !IsDefined(this.run) || !this.run.Live(this.game) { return; }
    MassOverrideHack.Beat(this.game, this.targets, this.lit, 1.0);
    MassOverrideInk.Beat(this.run, this.lit, 1.0, this.tick);
    MassOverrideLights.Beat(this.run, this.lit, 1.0, this.tick);
    if this.lit {
      MassOverrideCity.Lit(this.game);
    } else {
      MassOverrideCity.Dark(this.game);
    }
    if MassOverridePeople.Due(this.tick, MassOverridePulse.Interval()) && !this.run.farOff {
      let player: ref<PlayerPuppet> = this.player;
      MassOverridePeople.Panic(player);
      MassOverrideCars.Rehack(this.game, this.targets);
    }
    let next: ref<MassOverridePulse> = new MassOverridePulse();
    next.game = this.game;
    next.player = this.player;
    next.targets = this.targets;
    next.run = this.run;
    next.tick = this.tick + 1;
    next.lit = !this.lit;
    GameInstance.GetDelaySystem(this.game).DelayCallback(next, MassOverridePulse.Interval(), false);
  }
}

// Blackout mode: the power failing. Four times a second each strobed light draws its
// own state, mostly dark, and the city's lights flicker once a second the same way;
// the machines and screens glitch, the panic and the cars' hack are renewed. Like
// the pulse it stops before the revert, which puts every light back.
public class MassOverrideHold extends DelayCallback {
  public let game: GameInstance;
  public let player: wref<PlayerPuppet>;
  public let targets: array<ref<MassOverrideTarget>>;
  public let run: ref<MassOverrideRun>;
  public let tick: Int32;

  public static func Interval() -> Float { return 0.25; }
  // How often a light is lit on a given beat: low, so the street reads as failing.
  public static func Chance() -> Float { return 0.3; }

  public func Call() -> Void {
    if !IsDefined(this.run) || !this.run.Live(this.game) { return; }
    MassOverrideHack.Beat(this.game, this.targets, false, MassOverrideHold.Chance());
    MassOverrideInk.Beat(this.run, false, MassOverrideHold.Chance(), this.tick);
    MassOverrideLights.Beat(this.run, false, MassOverrideHold.Chance(), this.tick);
    let rounds: Int32 = this.tick / 4;
    if this.tick - rounds * 4 == 0 {
      if RandF() < MassOverrideHold.Chance() {
        MassOverrideCity.Lit(this.game);
      } else {
        MassOverrideCity.Dark(this.game);
      }
    }
    if MassOverridePeople.Due(this.tick, MassOverrideHold.Interval()) && !this.run.farOff {
      let player: ref<PlayerPuppet> = this.player;
      MassOverridePeople.Panic(player);
      MassOverrideCars.Rehack(this.game, this.targets);
    }
    let next: ref<MassOverrideHold> = new MassOverrideHold();
    next.game = this.game;
    next.player = this.player;
    next.targets = this.targets;
    next.run = this.run;
    next.tick = this.tick + 1;
    GameInstance.GetDelaySystem(this.game).DelayCallback(next, MassOverrideHold.Interval(), false);
  }
}

// Puts everything back when the effect's duration ends. Dismissing Capri does not
// end it early, so this runs on the delay system rather than on Capri. Each target
// gets back exactly what this cast did to it, through its own controller, which is
// there whether or not the device is still streamed in: the glitch stopped, the
// light set to the state it had at the cast, the car alarm off, the attitude
// neutral; and the city light request is removed so the timetable, the weather and
// quests decide again. The EMP sparks and the cars' Accelerate hack end by themselves.
public class MassOverrideRevert extends DelayCallback {
  public let game: GameInstance;
  public let player: wref<PlayerPuppet>;
  public let targets: array<ref<MassOverrideTarget>>;
  public let playerId: String;
  public let run: ref<MassOverrideRun>;
  public let remote: Bool;  // another player's cast run here
  public let seq: Int32;    // its seq at the gate
  public let id: Int32;     // which run on screen this is (MassOverridePrefs.SetActive)
  public let done: Bool;    // put back already (early, by the next cast): the scheduled call does nothing

  // Schedules the revert and makes its run the one on screen.
  public static func Arm(game: GameInstance, revert: ref<MassOverrideRevert>, seconds: Float) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if IsDefined(prefs) {
      revert.id = prefs.SetActive(revert);
    }
    GameInstance.GetDelaySystem(game).DelayCallback(revert, seconds, false);
  }

  // The run on screen, put back now: the next cast -- here or another player's -- saves the street as
  // it was, not halfway through a beat (it would then put the beat's colours back for good).
  public static func EndActive(game: GameInstance, why: String) -> Void {
    let prefs: ref<MassOverridePrefs> = MassOverridePrefs.Get();
    if !IsDefined(prefs) { return; }
    let active: ref<MassOverrideRevert> = prefs.Active();
    if IsDefined(active) && !active.done {
      let whose: String = "this game's cast";
      if active.remote {
        whose = "another player's cast seq=" + ToString(active.seq);
      }
      MassOverrideLog.Write("the run on screen (" + whose + ") ends early: " + why);
      active.Call();
    }
  }

  public func Call() -> Void {
    if this.done { return; }
    this.done = true;
    if IsDefined(this.run) { this.run.ended = true; }
    let player: ref<PlayerPuppet> = this.player;
    let inkBack: Int32 = MassOverrideInk.Restore(this.run);
    let lightsBack: Int32 = MassOverrideLights.Restore(this.run);
    if !IsDefined(this.run) || !this.run.farOff {
      MassOverrideFx.Burst(this.game, player, 0.6);
    }
    let released: Bool = MassOverrideCity.Release(this.game);
    let unglitched: Int32 = 0;
    let relit: Int32 = 0;
    let restored: Int32 = 0;
    let silenced: Int32 = 0;
    let calmed: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(this.targets) {
      let target: ref<MassOverrideTarget> = this.targets[i];
      let object: ref<GameObject> = GameInstance.FindEntityByID(this.game, target.entityId) as GameObject;
      if target.kind == MassOverrideKind.Person() {
        MassOverrideEffects.SetHostile(object as NPCPuppet, player, false);
        calmed += 1;
      } else {
        if target.kind == MassOverrideKind.Vehicle() {
          if target.alarm {
            MassOverrideCars.Silence(object as VehicleObject);
            silenced += 1;
          }
        } else {
          if target.glitch && MassOverrideHack.Unglitch(target, this.game) {
            unglitched += 1;
          }
          if target.strobe && MassOverrideHack.StrobeRestore(target, this.game) {
            relit += 1;
          }
          if target.cut && MassOverridePower.RestoreTarget(target, this.game) {
            restored += 1;
          }
        }
      }
      i += 1;
    }
    MassOverrideLog.Write("revert ink=" + ToString(inkBack) + " lights=" + ToString(lightsBack) + " unglitched=" + ToString(unglitched) + " relit=" + ToString(relit) + " restored=" + ToString(restored)
      + " silenced=" + ToString(silenced) + " calmed=" + ToString(calmed) + " city=" + (released ? "released" : "missing"));
    MassOverrideCastPost.Report(this.game, "{\"phase\":\"" + (this.remote ? "remote-revert" : "revert") + "\",\"playerId\":" + MassOverrideLog.Quote(this.playerId)
      + ",\"build\":\"" + MassOverrideBuild.Version() + "\""
      + ",\"seq\":" + ToString(this.seq)
      + ",\"cityReleased\":" + (released ? "true" : "false")
      + ",\"ink\":" + ToString(inkBack)
      + ",\"lightComponents\":" + ToString(lightsBack)
      + ",\"unglitched\":" + ToString(unglitched)
      + ",\"relit\":" + ToString(relit)
      + ",\"restored\":" + ToString(restored)
      + ",\"silenced\":" + ToString(silenced)
      + ",\"calmed\":" + ToString(calmed) + "}");
    MassOverrideLog.Flush(this.game, this.playerId, "revert");
  }
}

// What actually took, read back from the devices' controllers and the cars. The cast's
// own report can only say what was asked: every switch runs on the device's next
// update. "verify" is read two seconds into the cast, "settled" two seconds after the
// revert (nothing should still glitch, every light should be back as it was, no alarm
// ringing) and "final" a few seconds later, after the last picture.
public class MassOverrideVerify extends DelayCallback {
  public let game: GameInstance;
  public let playerId: String;
  public let phase: String;
  public let mode: String;
  public let targets: array<ref<MassOverrideTarget>>;

  public static func Delay() -> Float { return 2.0; }

  public func Call() -> Void {
    let glitched: Int32 = 0;
    let glitching: Int32 = 0;
    let emp: Int32 = 0;
    let strobed: Int32 = 0;
    let strobeOn: Int32 = 0;
    let strobeAsBefore: Int32 = 0;
    let cars: Int32 = 0;
    let accelerating: Int32 = 0;
    let panicDriving: Int32 = 0;
    let alarms: Int32 = 0;
    let alarmsOn: Int32 = 0;
    let gone: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(this.targets) {
      let target: ref<MassOverrideTarget> = this.targets[i];
      let object: ref<GameObject> = GameInstance.FindEntityByID(this.game, target.entityId) as GameObject;
      if target.glitch {
        glitched += 1;
        if MassOverrideHack.Glitching(target, this.game) { glitching += 1; }
      }
      if target.emp { emp += 1; }
      if target.strobe {
        strobed += 1;
        let on: Bool = MassOverrideHack.IsOn(target, this.game);
        if on { strobeOn += 1; }
        if on == target.stateOn { strobeAsBefore += 1; }
      }
      if target.hacked {
        cars += 1;
        let vehicle: ref<VehicleObject> = object as VehicleObject;
        if IsDefined(vehicle) {
          if vehicle.IsVehicleAccelerateQuickhackActive() { accelerating += 1; }
          if vehicle.IsPerformingPanicDriving() { panicDriving += 1; }
        } else {
          gone += 1;
        }
      }
      if target.alarm {
        alarms += 1;
        if IsDefined(object) {
          if MassOverrideCars.Ringing(object as VehicleObject) { alarmsOn += 1; }
        } else {
          if !target.hacked { gone += 1; }
        }
      }
      i += 1;
    }
    let city: String = MassOverrideCity.StateName(this.game);
    MassOverrideLog.Write(this.phase + " city=" + city + " glitching=" + ToString(glitching) + "/" + ToString(glitched)
      + " strobeOn=" + ToString(strobeOn) + "/" + ToString(strobed) + " asBefore=" + ToString(strobeAsBefore)
      + " accelerating=" + ToString(accelerating) + "/" + ToString(cars) + " panicDriving=" + ToString(panicDriving)
      + " alarmsOn=" + ToString(alarmsOn) + "/" + ToString(alarms) + " gone=" + ToString(gone));
    MassOverrideCastPost.Report(this.game, "{\"phase\":\"" + this.phase + "\",\"playerId\":" + MassOverrideLog.Quote(this.playerId)
      + ",\"build\":\"" + MassOverrideBuild.Version() + "\""
      + ",\"mode\":\"" + this.mode + "\""
      + ",\"city\":\"" + city + "\""
      + ",\"glitched\":" + ToString(glitched)
      + ",\"glitching\":" + ToString(glitching)
      + ",\"emp\":" + ToString(emp)
      + ",\"strobed\":" + ToString(strobed)
      + ",\"strobeOn\":" + ToString(strobeOn)
      + ",\"strobeAsBefore\":" + ToString(strobeAsBefore)
      + ",\"cars\":" + ToString(cars)
      + ",\"accelerating\":" + ToString(accelerating)
      + ",\"panicDriving\":" + ToString(panicDriving)
      + ",\"alarms\":" + ToString(alarms)
      + ",\"alarmsOn\":" + ToString(alarmsOn)
      + ",\"gone\":" + ToString(gone) + "}");
    MassOverrideLog.Flush(this.game, this.playerId, this.phase);
  }
}

// The build every report names, so a report can never be mistaken for one from the
// copy a running game loaded before an update.
public class MassOverrideBuild {
  public static func Version() -> String { return "1.16.15"; }
}

// CITY LIGHTS. The street lamps, building lights and neon that come on at dusk are not
// reachable one by one: they are ElectricLight devices wired to fuses, and the fuses
// answer to the City Light System (core/systems/cityLightSystem.script in the REDmod
// sources that ship with the game). That system takes a forced state from anyone --
// the rain listener asks for ForcedON, quests ask for ForcedOFF -- on a priority stack,
// and each fuse then walks its own lights with the authored stagger. Mass Override
// asks under its own source name and removes exactly that entry at the revert
// (DEFAULT for the same source), so the weather's or a quest's own request is left as
// it was. savable is false: a save taken mid-cast never loads into a dark city.
// Only lights that are on can go out. In daylight the timetable has them off already,
// which is why every report carries the in-game hour.
public class MassOverrideCity {
  public static func Source() -> CName { return n"CapriMassOverride"; }

  public static func System(game: GameInstance) -> ref<CityLightSystem> {
    return GameInstance.GetScriptableSystemsContainer(game).Get(n"CityLightSystem") as CityLightSystem;
  }

  public static func Force(game: GameInstance, state: ECLSForcedState) -> Bool {
    let system: ref<CityLightSystem> = MassOverrideCity.System(game);
    if !IsDefined(system) { return false; }
    let request: ref<ForceCLSStateRequest> = new ForceCLSStateRequest();
    request.state = state;
    request.sourceName = MassOverrideCity.Source();
    request.priority = EPriority.VeryHigh;
    request.removePreviousRequests = true;
    request.savable = false;
    system.QueueRequest(request);
    return true;
  }

  public static func Dark(game: GameInstance) -> Bool {
    return MassOverrideCity.Force(game, ECLSForcedState.ForcedOFF);
  }

  public static func Lit(game: GameInstance) -> Bool {
    return MassOverrideCity.Force(game, ECLSForcedState.ForcedON);
  }

  // Removes this source's request only; whatever else is on the stack takes over.
  public static func Release(game: GameInstance) -> Bool {
    return MassOverrideCity.Force(game, ECLSForcedState.DEFAULT);
  }

  public static func StateName(game: GameInstance) -> String {
    let system: ref<CityLightSystem> = MassOverrideCity.System(game);
    if !IsDefined(system) { return "missing"; }
    let state: ECLSForcedState = system.GetState();
    if Equals(state, ECLSForcedState.ForcedOFF) { return "forcedOff"; }
    if Equals(state, ECLSForcedState.ForcedON) { return "forcedOn"; }
    return "default";
  }

  public static func Fuses(game: GameInstance) -> Int32 {
    let system: ref<CityLightSystem> = MassOverrideCity.System(game);
    if !IsDefined(system) { return -1; }
    return system.GetFusesCount();
  }

  public static func Lights(game: GameInstance) -> Int32 {
    let system: ref<CityLightSystem> = MassOverrideCity.System(game);
    if !IsDefined(system) { return -1; }
    return system.GetLightsCount();
  }

  public static func Hour(game: GameInstance) -> Int32 {
    return GameTime.Hours(GameInstance.GetTimeSystem(game).GetGameTime());
  }
}

// SCREENS AND DEVICE LIGHTS go dark the way a fuse-box overload darkens them: the
// device's own controller is sent SetDeviceUnpowered (scriptableDeviceBasePS.script),
// which caches the state it was in, sets UNPOWERED and has the device run CutPower ->
// TurnOffDevice -- the same screen and light switches the old component pass made,
// but owned by the device, so its controller stops switching them back on a frame
// later. SetDevicePowered puts back the cached state, ON or OFF, and the device
// switches its own screens and lights to match. Nothing touches the components
// directly any more: a light component disabled from outside stays dark even after
// its device turns it back on.
// Only classes whose power-off is purely visual are listed: doors, gates, terminals,
// cameras, turrets, loot and traps are found and reported, and left alone.
public class MassOverridePower {
  public static func Allowed(object: ref<GameObject>) -> Bool {
    if !IsDefined(object) { return false; }
    if IsDefined(object as VendingMachine) { return true; }
    if IsDefined(object as TV) { return true; }
    if IsDefined(object as LcdScreen) { return true; }
    if IsDefined(object as BillboardDevice) { return true; }
    if IsDefined(object as InteractiveAd) { return true; }
    if IsDefined(object as AnimatedSign) { return true; }
    if IsDefined(object as InteractiveSign) { return true; }
    if IsDefined(object as ArcadeMachine) { return true; }
    if IsDefined(object as Jukebox) { return true; }
    if IsDefined(object as Radio) { return true; }
    if IsDefined(object as Speaker) { return true; }
    if IsDefined(object as ElectricLight) { return true; }
    if IsDefined(object as BlindingLight) { return true; }
    if IsDefined(object as TrafficLight) { return true; }
    return false;
  }

  public static func Controller(object: ref<GameObject>) -> ref<ScriptableDeviceComponentPS> {
    let device: ref<Device> = object as Device;
    if !IsDefined(device) { return null; }
    return device.GetDevicePS();
  }

  // True when a power cut was sent. A device that is broken, or already without
  // power, is left as it is and is not restored later either.
  public static func Cut(object: ref<GameObject>) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverridePower.Controller(object);
    if !IsDefined(ps) { return false; }
    if ps.IsDisabled() || ps.IsUnpowered() { return false; }
    ps.ExecutePSAction(ps.ActionSetDeviceUnpowered());
    return true;
  }

  public static func Restore(object: ref<GameObject>) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverridePower.Controller(object);
    if !IsDefined(ps) { return false; }
    if !ps.IsUnpowered() { return false; }
    ps.ExecutePSAction(ps.ActionSetDevicePowered());
    return true;
  }

  // The cut, remembered on the target with the controller it went to (see target.ps).
  public static func CutTarget(target: ref<MassOverrideTarget>, object: ref<GameObject>) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverridePower.Controller(object);
    if !IsDefined(ps) { return false; }
    if ps.IsDisabled() || ps.IsUnpowered() { return false; }
    ps.ExecutePSAction(ps.ActionSetDeviceUnpowered());
    target.cut = true;
    target.ps = ps;
    return true;
  }

  // Power back through the controller the cast cut, which does not need the device to be
  // streamed in: the controller is persistent, and a device that attaches later reads
  // its state from it.
  public static func RestoreTarget(target: ref<MassOverrideTarget>, game: GameInstance) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = target.ps;
    if !IsDefined(ps) {
      ps = MassOverridePower.Controller(GameInstance.FindEntityByID(game, target.entityId) as GameObject);
    }
    if !IsDefined(ps) { return false; }
    if !ps.IsUnpowered() { return false; }
    ps.ExecutePSAction(ps.ActionSetDevicePowered());
    return true;
  }

  public static func TargetIsCut(target: ref<MassOverrideTarget>, game: GameInstance) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = target.ps;
    if !IsDefined(ps) {
      ps = MassOverridePower.Controller(GameInstance.FindEntityByID(game, target.entityId) as GameObject);
    }
    if !IsDefined(ps) { return false; }
    return ps.IsUnpowered();
  }

  public static func IsCut(object: ref<GameObject>) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverridePower.Controller(object);
    if !IsDefined(ps) { return false; }
    return ps.IsUnpowered();
  }

  // Traffic lights are the one device the cut does not keep dark: the traffic
  // system's colour change re-lights the bulbs without looking at the device state
  // (trafficLight.script: OnTrafficLightChangeEvent), so the hold re-darkens them.
  public static func NeedsHold(object: ref<GameObject>) -> Bool {
    return IsDefined(object as TrafficLight);
  }
}

// HACKS. What V's own quickhacks do to a device, sent through the device's controller
// so the device plays it the way the game does (cyberpunk/devices in the REDmod
// sources). QuestStartGlitch -> Device.OnQuestStartGlitch -> StartGlitching, which on a
// vending machine is HackedEffect (cans thrown out) + AdvertGlitch + the glitch sound
// (vendingMachine.script), and on a TV, LCD screen, billboard, arcade, jukebox, radio
// or speaker its own picture or sound glitch; QuestStopGlitch ends it. The sparks are
// the EMP grenade's (interactiveDevice.script: OnEMPHitEvent -> 'emp_hit') and end on
// their own after `lifetime`; a device whose template has no such effect shows nothing
// and loses nothing. Lights are switched ON and OFF with the actions a light switch
// sends (SetDeviceON / SetDeviceOFF -> TurnOnDevice / TurnOffDevice), which light a
// street lamp the timetable keeps off by day; the revert puts back the state each one
// had. Nothing is unpowered, so a glitching screen stays visible while it glitches.
public class MassOverrideHack {
  // Devices whose StartGlitching is a picture or sound glitch and nothing more.
  // Terminals, fuse boxes, alarms and data terms glitch too, but there the glitch is
  // gameplay (security, fast travel), so they are left alone.
  public static func Glitchable(object: ref<GameObject>) -> Bool {
    if !IsDefined(object) { return false; }
    if IsDefined(object as VendingMachine) { return true; }
    if IsDefined(object as TV) { return true; }
    if IsDefined(object as LcdScreen) { return true; }
    if IsDefined(object as BillboardDevice) { return true; }
    if IsDefined(object as ArcadeMachine) { return true; }
    if IsDefined(object as Jukebox) { return true; }
    if IsDefined(object as Radio) { return true; }
    if IsDefined(object as Speaker) { return true; }
    if IsDefined(object as HoloTable) { return true; }
    if IsDefined(object as NcartTimetable) { return true; }
    if IsDefined(object as RetractableAd) { return true; }
    return false;
  }

  // Devices whose ON/OFF is light and nothing else: lamps and exit signs, spotlights,
  // traffic, crossing and zebra lights, and the signs and ads with no glitch of their
  // own. Alarm lights belong to security systems and are left alone.
  public static func Strobable(object: ref<GameObject>) -> Bool {
    if !IsDefined(object) { return false; }
    if IsDefined(object as ElectricLight) { return true; }
    if IsDefined(object as BlindingLight) { return true; }
    if IsDefined(object as TrafficLight) { return true; }
    if IsDefined(object as GameplayLight) { return true; }
    if IsDefined(object as InteractiveAd) { return true; }
    if IsDefined(object as AnimatedSign) { return true; }
    if IsDefined(object as InteractiveSign) { return true; }
    return false;
  }

  // The controller this cast used, kept on the target so the revert reaches it after
  // the device has streamed out; otherwise the one of the device in the world now.
  public static func Controller(target: ref<MassOverrideTarget>, game: GameInstance) -> ref<ScriptableDeviceComponentPS> {
    if IsDefined(target.ps) { return target.ps; }
    return MassOverridePower.Controller(GameInstance.FindEntityByID(game, target.entityId) as GameObject);
  }

  // True when the glitch was sent. A broken or unpowered device, or one already
  // glitching for some other reason, is left as it is and not stopped later either.
  public static func Glitch(target: ref<MassOverrideTarget>, object: ref<GameObject>) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverridePower.Controller(object);
    if !IsDefined(ps) { return false; }
    if ps.IsDisabled() || ps.IsUnpowered() || ps.IsGlitching() { return false; }
    if !ps.CapriMassOverrideGlitch(true) { return false; }
    target.ps = ps;
    target.glitch = true;
    return true;
  }

  public static func Unglitch(target: ref<MassOverrideTarget>, game: GameInstance) -> Bool {
    if !target.glitch { return false; }
    let ps: ref<ScriptableDeviceComponentPS> = MassOverrideHack.Controller(target, game);
    if !IsDefined(ps) { return false; }
    return ps.CapriMassOverrideGlitch(false);
  }

  public static func Glitching(target: ref<MassOverrideTarget>, game: GameInstance) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverrideHack.Controller(target, game);
    if !IsDefined(ps) { return false; }
    return ps.IsGlitching();
  }

  // The EMP grenade's sparks on an interactive device, for `seconds`.
  public static func Emp(target: ref<MassOverrideTarget>, object: ref<GameObject>, seconds: Float) -> Bool {
    if !IsDefined(object as InteractiveDevice) { return false; }
    let evt: ref<EMPHitEvent> = new EMPHitEvent();
    evt.lifetime = seconds;
    object.QueueEvent(evt);
    target.emp = true;
    return true;
  }

  // A light switch: ON or OFF through the controller. Nothing without power, or broken.
  public static func Switch(ps: ref<ScriptableDeviceComponentPS>, on: Bool) -> Bool {
    if !IsDefined(ps) { return false; }
    if ps.IsDisabled() || ps.IsUnpowered() { return false; }
    if on {
      ps.ExecutePSAction(ps.ActionSetDeviceON());
    } else {
      ps.ExecutePSAction(ps.ActionSetDeviceOFF());
    }
    return true;
  }

  // Puts a light on the beat: remembers whether it was ON and switches it to `first`
  // at once, so the cast itself is the first visible change.
  public static func StrobeStart(target: ref<MassOverrideTarget>, object: ref<GameObject>, first: Bool) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverridePower.Controller(object);
    if !IsDefined(ps) { return false; }
    if ps.IsDisabled() || ps.IsUnpowered() { return false; }
    target.ps = ps;
    target.strobe = true;
    target.stateOn = Equals(ps.GetDeviceState(), EDeviceStatus.ON);
    MassOverrideHack.Switch(ps, first);
    return true;
  }

  // One beat for every strobed light. `on` is the state the beat switches to; with
  // `chance` below 1.0 each light draws its own instead (the blackout's flicker).
  public static func Beat(game: GameInstance, targets: array<ref<MassOverrideTarget>>, on: Bool, chance: Float) -> Int32 {
    let switched: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      let target: ref<MassOverrideTarget> = targets[i];
      if target.strobe {
        let state: Bool = on;
        if chance < 1.0 {
          state = RandF() < chance;
        }
        if MassOverrideHack.Switch(MassOverrideHack.Controller(target, game), state) {
          switched += 1;
        }
      }
      i += 1;
    }
    return switched;
  }

  public static func StrobeRestore(target: ref<MassOverrideTarget>, game: GameInstance) -> Bool {
    if !target.strobe { return false; }
    return MassOverrideHack.Switch(MassOverrideHack.Controller(target, game), target.stateOn);
  }

  public static func IsOn(target: ref<MassOverrideTarget>, game: GameInstance) -> Bool {
    let ps: ref<ScriptableDeviceComponentPS> = MassOverrideHack.Controller(target, game);
    if !IsDefined(ps) { return false; }
    return Equals(ps.GetDeviceState(), EDeviceStatus.ON);
  }

  // Whether anyone could have seen it: inside the camera's frustum, and how close.
  public static func Seen(stats: ref<MassOverrideStats>, camera: ref<CameraSystem>, object: ref<GameObject>, here: Vector4) -> Void {
    if !IsDefined(object) { return; }
    if IsDefined(camera) && camera.IsInCameraFrustum(object, 2.0, 1.0) {
      stats.hackInView += 1;
    }
    let away: Float = Vector4.Distance(object.GetWorldPosition(), here);
    if stats.nearestHack < 0.0 || away < stats.nearestHack {
      stats.nearestHack = away;
    }
  }
}

// The glitch actions are protected on the controller, so the switch is added to the
// class itself, named for Capri so it cannot meet another mod's method. It sends the
// same QuestStartGlitch / QuestStopGlitch a quest sends (scriptableDeviceBasePS.script).
@addMethod(ScriptableDeviceComponentPS)
public func CapriMassOverrideGlitch(on: Bool) -> Bool {
  if this.IsDisabled() { return false; }
  if on {
    this.ExecutePSAction(this.ActionQuestStartGlitch());
  } else {
    this.ExecutePSAction(this.ActionQuestStopGlitch());
  }
  return true;
}

// CARS. A car with ambient crowd at the wheel gets what V's Accelerate quickhack does
// (vehicleComponentPS.script: OnVehicleOverrideAccelerate): high-priority panic driving
// and the native Accelerate hack, which floors it, and its alarm goes off as well. An
// empty, parked car's alarm goes off: set on its vehicle controller, the switch the
// Distract quickhack's ForceCarAlarm ends in (OnForceCarAlarm -> SetAlarm(true)), set
// directly because that action's own off-timer is the quickhack upload time, 0 outside
// a quickhack. A car someone else is in -- V, another player, a story NPC, a passenger
// -- only honks. V's cars, quest cars and wrecks are left alone.
public class MassOverrideCars {
  public static func None() -> Int32 { return 0; }
  public static func Alarm() -> Int32 { return 1; }
  public static func Honk() -> Int32 { return 2; }
  public static func Accelerate() -> Int32 { return 3; }

  public static func HonkSeconds() -> Float { return 3.0; }

  public static func Hack(game: GameInstance, vehicle: ref<VehicleObject>, target: ref<MassOverrideTarget>) -> Int32 {
    if !IsDefined(vehicle) || !IsDefined(target) { return MassOverrideCars.None(); }
    if vehicle.IsPlayerVehicle() || vehicle.IsDestroyed() || vehicle.IsQuest() {
      return MassOverrideCars.None();
    }
    let ps: ref<VehicleComponentPS> = vehicle.GetVehiclePS();
    if MassOverrideCars.CrowdDriven(game, vehicle) {
      vehicle.EnableHighPriorityPanicDriving();
      vehicle.ActivateNetrunnerQuickhack(VehicleNetrunnerQuickhackType.Accelerate);
      target.hacked = true;
      if IsDefined(ps) && ps.CapriMassOverrideCarAlarm(true) {
        target.alarm = true;
      }
      return MassOverrideCars.Accelerate();
    }
    if VehicleComponent.GetNumberOfOccupiedSlots(game, vehicle) == 0 {
      if IsDefined(ps) && ps.CapriMassOverrideCarAlarm(true) {
        target.alarm = true;
        return MassOverrideCars.Alarm();
      }
      return MassOverrideCars.None();
    }
    let horn: ref<VehicleQuestHornEvent> = new VehicleQuestHornEvent();
    horn.honkTime = MassOverrideCars.HonkSeconds();
    vehicle.QueueEvent(horn);
    return MassOverrideCars.Honk();
  }

  // The driver, when it is ambient crowd. V, other players and story NPCs never are.
  public static func CrowdDriven(game: GameInstance, vehicle: ref<VehicleObject>) -> Bool {
    if !IsDefined(vehicle) { return false; }
    let mounted: ref<GameObject> = VehicleComponent.GetDriverMounted(game, vehicle.GetEntityID());
    let driver: ref<ScriptedPuppet> = mounted as ScriptedPuppet;
    if !IsDefined(driver) { return false; }
    if driver.IsPlayer() { return false; }
    return driver.IsCrowd();
  }

  // The Accelerate hack runs for its own tweaked duration; renewed on the panic's
  // beat for the cars this cast hacked that are still driven and no longer under it.
  public static func Rehack(game: GameInstance, targets: array<ref<MassOverrideTarget>>) -> Int32 {
    let renewed: Int32 = 0;
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].hacked {
        let vehicle: ref<VehicleObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as VehicleObject;
        if IsDefined(vehicle) && !vehicle.IsDestroyed() && !vehicle.IsVehicleAccelerateQuickhackActive()
            && MassOverrideCars.CrowdDriven(game, vehicle) {
          vehicle.EnableHighPriorityPanicDriving();
          vehicle.ActivateNetrunnerQuickhack(VehicleNetrunnerQuickhackType.Accelerate);
          renewed += 1;
        }
      }
      i += 1;
    }
    return renewed;
  }

  public static func Silence(vehicle: ref<VehicleObject>) -> Void {
    if !IsDefined(vehicle) { return; }
    let ps: ref<VehicleComponentPS> = vehicle.GetVehiclePS();
    if IsDefined(ps) {
      ps.CapriMassOverrideCarAlarm(false);
    }
  }

  public static func Ringing(vehicle: ref<VehicleObject>) -> Bool {
    if !IsDefined(vehicle) { return false; }
    let ps: ref<VehicleComponentPS> = vehicle.GetVehiclePS();
    if !IsDefined(ps) { return false; }
    return ps.CapriMassOverrideCarAlarmOn();
  }
}

// GetVehicleControllerPS is private on VehicleComponentPS, so the alarm switch is
// added to the class itself. Named for Capri, so it cannot meet another mod's method.
@addMethod(VehicleComponentPS)
public func CapriMassOverrideCarAlarm(on: Bool) -> Bool {
  let controller: ref<vehicleControllerPS> = this.GetVehicleControllerPS();
  if !IsDefined(controller) { return false; }
  controller.SetAlarm(on);
  return true;
}

@addMethod(VehicleComponentPS)
public func CapriMassOverrideCarAlarmOn() -> Bool {
  let controller: ref<vehicleControllerPS> = this.GetVehicleControllerPS();
  if !IsDefined(controller) { return false; }
  return controller.IsAlarmOn();
}

// PEOPLE. The attitude switch alone changed a flag nobody could see. This is the
// panic MaxTac's arrival causes (psychoSquadAVSystem.script broadcasts Terror from the
// player at 100 m): civilians scream, run and cower. It is broadcast from V at the
// cast and renewed every few seconds for the duration, and each person the probe
// found also gets it directly, so someone out of V's line still reacts.
public class MassOverridePeople {
  public static func Radius() -> Float { return 60.0; }
  public static func RepeatSeconds() -> Float { return 6.0; }

  public static func Panic(player: ref<PlayerPuppet>) -> Int32 {
    if !IsDefined(player) { return 0; }
    StimBroadcasterComponent.BroadcastStim(player, gamedataStimType.Terror, MassOverridePeople.Radius());
    return 1;
  }

  public static func Scare(player: ref<PlayerPuppet>, npc: ref<NPCPuppet>) -> Bool {
    if !IsDefined(player) || !IsDefined(npc) { return false; }
    StimBroadcasterComponent.SendStimDirectly(player, gamedataStimType.Terror, npc);
    return true;
  }

  // True on the ticks that renew the panic. Division and subtraction rather than a
  // modulo, as elsewhere in these files.
  public static func Due(tick: Int32, interval: Float) -> Bool {
    let every: Int32 = RoundF(MassOverridePeople.RepeatSeconds() / interval);
    if every <= 0 || tick <= 0 { return false; }
    let rounds: Int32 = tick / every;
    return tick - rounds * every == 0;
  }
}

// DEVICES THE PROBE CANNOT SEE. The targeting system only returns entities that carry
// a targeting component -- what V can scan or hack -- so a live cast in Japantown found
// vending machines, door panels and traffic lights and not one TV, billboard, sign or
// lamp. Codeware's entity lifecycle callbacks report every device of a listed class
// as it streams in and out; this keeps the ids of the ones attached right now, keyed
// by the id itself, and a cast asks it for those near V.
public class MassOverrideDeviceEntry {
  public let entityId: EntityID;
}

public class MassOverrideRegistry extends ScriptableSystem {
  private let m_devices: ref<inkHashMap>;
  private let m_size: Int32;     // entries held now
  private let m_attached: Int32; // attach events seen this session
  private let m_detached: Int32; // detach events seen this session

  public static func Get(game: GameInstance) -> ref<MassOverrideRegistry> {
    let system: ref<MassOverrideRegistry> =
      GameInstance.GetScriptableSystemsContainer(game).Get(n"MassOverrideRegistry") as MassOverrideRegistry;
    if IsDefined(system) { return system; }
    return GameInstance.GetScriptableSystemsContainer(game).Get(n"Open77.MassOverrideRegistry") as MassOverrideRegistry;
  }

  private func OnAttach() -> Void {
    // every game follows the gate's feed from the start of its session (not only after it cast)
    MassOverrideFeed.Start(this.GetGameInstance(), "session start");
    this.m_devices = new inkHashMap();
    let callbacks: ref<CallbackSystem> = GameInstance.GetCallbackSystem();
    MassOverrideRegistry.Targets(callbacks.RegisterCallback(n"Entity/Attach", this, n"OnDeviceAttach"));
    MassOverrideRegistry.Targets(callbacks.RegisterCallback(n"Entity/Detach", this, n"OnDeviceDetach"));
  }

  private func OnDetach() -> Void {
    let callbacks: ref<CallbackSystem> = GameInstance.GetCallbackSystem();
    callbacks.UnregisterCallback(n"Entity/Attach", this, n"OnDeviceAttach");
    callbacks.UnregisterCallback(n"Entity/Detach", this, n"OnDeviceDetach");
  }

  // The classes MassOverridePower switches. The subclasses are listed as well, in
  // case a type target only matches the exact class; a device reported twice is
  // simply stored once.
  public static func Targets(handler: ref<CallbackSystemHandler>) -> Void {
    if !IsDefined(handler) { return; }
    handler.AddTarget(EntityTarget.Type(n"VendingMachine"));
    handler.AddTarget(EntityTarget.Type(n"WeaponVendingMachine"));
    handler.AddTarget(EntityTarget.Type(n"IceMachine"));
    handler.AddTarget(EntityTarget.Type(n"TV"));
    handler.AddTarget(EntityTarget.Type(n"WallScreen"));
    handler.AddTarget(EntityTarget.Type(n"LcdScreen"));
    handler.AddTarget(EntityTarget.Type(n"ApartmentScreen"));
    handler.AddTarget(EntityTarget.Type(n"BillboardDevice"));
    handler.AddTarget(EntityTarget.Type(n"InteractiveAd"));
    handler.AddTarget(EntityTarget.Type(n"AnimatedSign"));
    handler.AddTarget(EntityTarget.Type(n"InteractiveSign"));
    handler.AddTarget(EntityTarget.Type(n"ArcadeMachine"));
    handler.AddTarget(EntityTarget.Type(n"PachinkoMachine"));
    handler.AddTarget(EntityTarget.Type(n"Jukebox"));
    handler.AddTarget(EntityTarget.Type(n"Radio"));
    handler.AddTarget(EntityTarget.Type(n"Speaker"));
    handler.AddTarget(EntityTarget.Type(n"ElectricLight"));
    handler.AddTarget(EntityTarget.Type(n"ExitLight"));
    handler.AddTarget(EntityTarget.Type(n"BlindingLight"));
    handler.AddTarget(EntityTarget.Type(n"Reflector"));
    handler.AddTarget(EntityTarget.Type(n"TrafficLight"));
    handler.AddTarget(EntityTarget.Type(n"TrafficZebra"));
    handler.AddTarget(EntityTarget.Type(n"CrossingLight"));
  }

  private cb func OnDeviceAttach(event: ref<EntityLifecycleEvent>) {
    let entity: wref<Entity> = event.GetEntity();
    if !IsDefined(entity) || !IsDefined(this.m_devices) { return; }
    this.m_attached += 1;
    let id: EntityID = entity.GetEntityID();
    let key: Uint64 = Cast<Uint64>(id);
    let entry: ref<MassOverrideDeviceEntry> = new MassOverrideDeviceEntry();
    entry.entityId = id;
    if this.m_devices.KeyExist(key) {
      this.m_devices.Set(key, entry);
    } else {
      this.m_devices.Insert(key, entry);
      this.m_size += 1;
    }
  }

  private cb func OnDeviceDetach(event: ref<EntityLifecycleEvent>) {
    let entity: wref<Entity> = event.GetEntity();
    if !IsDefined(entity) || !IsDefined(this.m_devices) { return; }
    this.m_detached += 1;
    let key: Uint64 = Cast<Uint64>(entity.GetEntityID());
    if this.m_devices.KeyExist(key) {
      this.m_devices.Remove(key);
      this.m_size -= 1;
    }
  }

  // How far from V a registered device is still switched. Wider than the probe's first
  // reach: a billboard on a building across the street is often 80-120 m away and still
  // the brightest thing in view, and the registry only holds what is streamed in anyway.
  public static func Reach() -> Float { return 120.0; }

  public func Size() -> Int32 { return this.m_size; }
  public func AttachEvents() -> Int32 { return this.m_attached; }
  public func DetachEvents() -> Int32 { return this.m_detached; }

  // Ids of the devices held now that stand within `radius` of `origin`.
  public func Near(game: GameInstance, origin: Vector4, radius: Float) -> array<EntityID> {
    let out: array<EntityID>;
    if !IsDefined(this.m_devices) { return out; }
    let values: array<wref<IScriptable>>;
    this.m_devices.GetValues(values);
    for value in values {
      let entry: wref<MassOverrideDeviceEntry> = value as MassOverrideDeviceEntry;
      if IsDefined(entry) {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, entry.entityId) as GameObject;
        if IsDefined(object) && Vector4.Distance(object.GetWorldPosition(), origin) <= radius {
          ArrayPush(out, entry.entityId);
        }
      }
    }
    return out;
  }
}
