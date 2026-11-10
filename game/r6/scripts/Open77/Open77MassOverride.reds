// Mass Override: the sweep and the effects, in one place.
//
// Hostility is the same call Open77PlayerModels.reds uses:
// AttitudeAgent.SetAttitudeTowards(EAIAttitude.AIA_Hostile).
//
// Screens, billboards and TVs go through the component switch the vanilla device
// classes themselves use. In the source that ships with REDmod
// (tools/redmod/scripts):
//   cyberpunk/devices/billboard/billboard.script    -> m_advUiComponent.Toggle(bool)
//   cyberpunk/devices/homeAppliances/.../tv.script  -> m_uiComponent.Toggle(bool)
//   cyberpunk/devices/lcdScreens/lcdScreen.script   -> m_uiComponent.Toggle(bool)
// so this is the game's own switch, not a guess. The widget component NAME
// differs per device ('ui', 'ads', 'tv_ui', 'radio_ui', 'terminalui'), so
// components are chosen by class instead of by name.
//
// Lights use the same component enable switch, on the gameLightComponent that
// ElectricLight requests for a street light or a lamp. vehicleLightComponent
// derives from it, so headlights match too. ToggleLightEvent itself is not in the
// redscript RTTI, which is why the component switch is used here rather than the
// event vanilla queues internally.
//
// Local test build only.

public class MassOverrideTarget {
  public let entityId: EntityID;
  public let kind: Int32;   // 0 = npc, 1 = screen, billboard, light or vehicle
  public let label: String; // class name, for the log
}

public class MassOverrideSweep {
  // The radius matches Open77ScriptBridge's TargetSearchQuery (40 m).
  public static func Collect(player: ref<PlayerPuppet>, radius: Float, cap: Int32) -> array<ref<MassOverrideTarget>> {
    let out: array<ref<MassOverrideTarget>>;
    let query: TargetSearchQuery;
    query.testedSet = TargetingSet.Complete;
    query.searchFilter = TSF_Any(
      TSFMV.Obj_Puppet | TSFMV.Obj_Device | TSFMV.Obj_Other |
      TSFMV.Att_Friendly | TSFMV.Att_Hostile | TSFMV.Att_Neutral |
      TSFMV.St_Alive | TSFMV.St_TurnedOn | TSFMV.St_TurnedOff);
    query.maxDistance = radius;
    query.filterObjectByDistance = true;
    query.includeSecondaryTargets = true;
    query.ignoreInstigator = true;
    let parts: array<TS_TargetPartInfo>;
    GameInstance.GetTargetingSystem(player.GetGame()).GetTargetParts(player, query, parts);
    let i: Int32 = 0;
    while i < ArraySize(parts) && ArraySize(out) < cap {
      let comp: wref<TargetingComponent> = TS_TargetPartInfo.GetComponent(parts[i]);
      if IsDefined(comp) {
        let entity: wref<Entity> = comp.GetEntity();
        if IsDefined(entity) {
          let npc: ref<NPCPuppet> = entity as NPCPuppet;
          if IsDefined(npc) {
            let target: ref<MassOverrideTarget> = new MassOverrideTarget();
            target.entityId = npc.GetEntityID();
            target.kind = 0;
            target.label = NameToString(npc.GetClassName());
            ArrayPush(out, target);
          } else {
            let device: ref<GameObject> = entity as GameObject;
            // Only things with a screen or a light are taken, so the cap is not
            // filled with chairs and crates that could not change anyway.
            if IsDefined(device) && MassOverrideEffects.CanBlink(device) {
              let screen: ref<MassOverrideTarget> = new MassOverrideTarget();
              screen.entityId = device.GetEntityID();
              screen.kind = 1;
              screen.label = NameToString(device.GetClassName());
              ArrayPush(out, screen);
            }
          }
        }
      }
      i += 1;
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
  // vehicle headlight).
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

  // A screen is any world widget component. A light is a gameLightComponent,
  // which is what ElectricLight requests for a street light or a lamp;
  // vehicleLightComponent derives from it, so headlights match too. Nothing else
  // on the entity is touched, so collision, meshes and interaction stay as they were.
  private static func IsBlinkable(component: ref<IComponent>) -> Bool {
    if !IsDefined(component) { return false; }
    if IsDefined(component as IWorldWidgetComponent) { return true; }
    return IsDefined(component as gameLightComponent);
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
