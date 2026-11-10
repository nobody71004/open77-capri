// Mass Override: the probe sweep, the per-area cache and the effects.
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
  private let m_next: Int32 = 1;    // what the next unpinned cast uses (1 = blackout)

  public static func Get() -> ref<MassOverridePrefs> {
    let service: ref<MassOverridePrefs> =
      GameInstance.GetScriptableServiceContainer().GetService(n"MassOverridePrefs") as MassOverridePrefs;
    if IsDefined(service) { return service; }
    return GameInstance.GetScriptableServiceContainer().GetService(n"Open77.MassOverridePrefs") as MassOverridePrefs;
  }

  // Each cast consumes one: this is the per-cast choice. A null service leaves the
  // caller on blink, so the fallback is the old behaviour rather than no effect.
  public func Mode() -> Int32 {
    if this.m_pinned >= 0 { return this.m_pinned; }
    let mode: Int32 = this.m_next;
    if mode == MassOverrideMode.Blink() {
      this.m_next = MassOverrideMode.Blackout();
    } else {
      this.m_next = MassOverrideMode.Blink();
    }
    return mode;
  }

  public func Pin(mode: Int32) -> Void { this.m_pinned = mode; }

  public func Auto() -> Void { this.m_pinned = -1; }

  public func Pinned() -> Bool { return this.m_pinned >= 0; }
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
  public let changed: Int32;  // components actually switched by the first pass
  public let cacheHit: Bool;  // the block's devices came from the cache
  public let blocks: Int32;   // areas the cache holds
  public let seconds: Float;  // wall of the whole cast, as the engine reports it
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
  // Reach of one probe. Smaller than the old single sweep, because the probes chain.
  public static func Reach() -> Float { return 25.0; }

  // Probes per cast. Each is one targeting query that returns its whole
  // neighbourhood, so this bounds the work a cast can do.
  public static func MaxProbes() -> Int32 { return 64; }

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
      return out;
    }
    let probed: array<ref<MassOverrideTarget>> = MassOverrideProbe.Fill(player, cap, true, stats);
    if IsDefined(cache) {
      cache.Remember(key, cell, probed);
      stats.blocks = cache.AreaCount();
    }
    return probed;
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
    while next < ArraySize(frontier) && probes < MassOverrideProbe.MaxProbes() && ArraySize(out) < cap {
      let anchor: ref<GameObject> = GameInstance.FindEntityByID(player.GetGame(), frontier[next]) as GameObject;
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
        query.maxDistance = MassOverrideProbe.Reach();
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

  // Every target back to the state it was found in.
  public static func RestoreAll(game: GameInstance, targets: array<ref<MassOverrideTarget>>) -> Void {
    let sink: ref<MassOverrideStats> = new MassOverrideStats();
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].kind != 0 {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as GameObject;
        MassOverrideEffects.Switch(object, targets[i].screenWasOn, targets[i].lightWasOn, sink);
      }
      i += 1;
    }
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

// Blink mode: pulses everything it was given until the duration runs out, then
// leaves the block lit. Each pulse re-arms itself on the delay system, so a
// dismissed Capri does not stop it.
public class MassOverridePulse extends DelayCallback {
  public let game: GameInstance;
  public let targets: array<ref<MassOverrideTarget>>;
  public let cyclesLeft: Int32;
  public let lit: Bool; // the state this pulse switches to

  public static func Interval() -> Float { return 1.0; }

  public func Call() -> Void {
    MassOverrideEffects.SetAll(this.game, this.targets, this.lit);
    if this.cyclesLeft > 1 {
      let next: ref<MassOverridePulse> = new MassOverridePulse();
      next.game = this.game;
      next.targets = this.targets;
      next.cyclesLeft = this.cyclesLeft - 1;
      next.lit = !this.lit;
      GameInstance.GetDelaySystem(this.game).DelayCallback(next, MassOverridePulse.Interval(), false);
    } else {
      // Whatever the last pulse did, end where the block started, not lit: a screen
      // that was off before the cast stays off.
      MassOverrideEffects.RestoreAll(this.game, this.targets);
    }
  }
}

// Blackout mode: re-asserts dark on a timer instead of switching once.
//
// A single Toggle(false) is not enough. A device's own controller keeps its screen
// and lights in step with its state, so it switches its component back on within a
// frame or two -- which is exactly why the blink survived (it re-asserts twice a
// second) while the one-shot blackout looked like nothing had happened at all.
// This holds the block dark for the whole duration and then lets the revert light
// it back up.
public class MassOverrideHold extends DelayCallback {
  public let game: GameInstance;
  public let targets: array<ref<MassOverrideTarget>>;
  public let cyclesLeft: Int32;

  public static func Interval() -> Float { return 1.0; }

  public func Call() -> Void {
    MassOverrideEffects.SetAll(this.game, this.targets, false);
    if this.cyclesLeft > 1 {
      let next: ref<MassOverrideHold> = new MassOverrideHold();
      next.game = this.game;
      next.targets = this.targets;
      next.cyclesLeft = this.cyclesLeft - 1;
      GameInstance.GetDelaySystem(this.game).DelayCallback(next, MassOverrideHold.Interval(), false);
    }
  }
}

// Puts everything back when the effect's duration ends. Dismissing Capri does
// not end it early, so this runs on the delay system rather than on Capri.
public class MassOverrideRevert extends DelayCallback {
  public let game: GameInstance;
  public let player: wref<PlayerPuppet>;
  public let targets: array<ref<MassOverrideTarget>>;

  public func Call() -> Void {
    let player: ref<PlayerPuppet> = this.player;
    let sink: ref<MassOverrideStats> = new MassOverrideStats();
    let i: Int32 = 0;
    while i < ArraySize(this.targets) {
      let target: ref<MassOverrideTarget> = this.targets[i];
      let object: ref<GameObject> = GameInstance.FindEntityByID(this.game, target.entityId) as GameObject;
      if target.kind == 0 {
        MassOverrideEffects.SetHostile(object as NPCPuppet, player, false);
      } else {
        // Each part back to the state it had before the cast, rather than on.
        MassOverrideEffects.Switch(object, target.screenWasOn, target.lightWasOn, sink);
      }
      i += 1;
    }
  }
}
