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
  public let kind: Int32;   // 0 = npc, 1 = screen, billboard, light or vehicle
  public let label: String; // class name, for the log
  public let area: String;  // 50 m cell the target stands in
}

// Kept as Int32 constants rather than an enum so the mode can be passed through a
// DelayCallback field and compared with a plain != , which compiles everywhere.
public class MassOverrideMode {
  // Pulse the lights and screens for the duration. Default.
  public static func Blink() -> Int32 { return 0; }
  // Hold them dark for the duration, then restore.
  public static func Blackout() -> Int32 { return 1; }
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
  public static func Collect(player: ref<PlayerPuppet>, cap: Int32) -> array<ref<MassOverrideTarget>> {
    let game: GameInstance = player.GetGame();
    let position: Vector4 = player.GetWorldPosition();
    let key: String = MassOverrideArea.Name(game, position);
    let cell: String = MassOverrideArea.Cell(position);
    let cache: ref<MassOverrideCache> = MassOverrideCache.Get();
    if IsDefined(cache) && cache.Known(key) {
      let out: array<ref<MassOverrideTarget>> = MassOverrideProbe.Fill(player, cap, false);
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
    let probed: array<ref<MassOverrideTarget>> = MassOverrideProbe.Fill(player, cap, true);
    if IsDefined(cache) {
      cache.Remember(key, cell, probed);
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
  public static func Fill(player: ref<PlayerPuppet>, cap: Int32, includeDevices: Bool) -> array<ref<MassOverrideTarget>> {
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
                  ArrayPush(out, person);
                }
              } else if includeDevices {
                let device: ref<GameObject> = entity as GameObject;
                if IsDefined(device) && !ArrayContains(seen, device.GetEntityID())
                  && MassOverrideEffects.CanBlink(device) {
                  ArrayPush(seen, device.GetEntityID());
                  let screen: ref<MassOverrideTarget> = new MassOverrideTarget();
                  screen.entityId = device.GetEntityID();
                  screen.kind = 1;
                  screen.label = NameToString(device.GetClassName());
                  screen.area = MassOverrideArea.Cell(device.GetWorldPosition());
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
  public static func Blink(target: ref<GameObject>, on: Bool) -> Int32 {
    if !IsDefined(target) { return 0; }
    let changed: Int32 = 0;
    let components: array<ref<IComponent>> = target.GetComponents();
    let i: Int32 = 0;
    while i < ArraySize(components) {
      let component: ref<IComponent> = components[i];
      if MassOverrideEffects.IsBlinkable(component) && component.IsEnabled() != on {
        component.Toggle(on);
        changed += 1;
      }
      i += 1;
    }
    return changed;
  }

  // One swipe of the whole target list: dark or lit. Used by the blackout (once
  // dark, restored at revert) and by each pulse of the blink.
  public static func SetAll(game: GameInstance, targets: array<ref<MassOverrideTarget>>, lit: Bool) -> Void {
    let i: Int32 = 0;
    while i < ArraySize(targets) {
      if targets[i].kind != 0 {
        let object: ref<GameObject> = GameInstance.FindEntityByID(game, targets[i].entityId) as GameObject;
        MassOverrideEffects.Blink(object, lit);
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
      // Whatever the last pulse did, end lit rather than dark.
      MassOverrideEffects.SetAll(this.game, this.targets, true);
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
    let i: Int32 = 0;
    while i < ArraySize(this.targets) {
      let target: ref<MassOverrideTarget> = this.targets[i];
      let object: ref<GameObject> = GameInstance.FindEntityByID(this.game, target.entityId) as GameObject;
      if target.kind == 0 {
        MassOverrideEffects.SetHostile(object as NPCPuppet, player, false);
      } else {
        MassOverrideEffects.Blink(object, true);
      }
      i += 1;
    }
  }
}
