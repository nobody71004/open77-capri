# Mass Override: design

Status: locked for execution. Items marked **TBD** need a decision or a spike result before the phase that depends on them.

## Summary

Mass Override is a Capri-only quickhack. Capri, the companion, triggers it from her own action code. It affects many devices and vehicles at once, in multiplayer from v1. It has no time dilation, and it does not use the Sandevistan code or dependency.

## Scope

In:
- Targets: lights, billboards, TVs and screens, cars, bikes and motorcycles.
- Effects: make targets hostile (vehicles and NPCs only), blink lights and screens, change screen content.
- Multiplayer from v1, server-authoritative.

Out (for now):
- Time dilation of any kind.
- Pedestrians (Phase 5 at the earliest).
- Any item, slot or keybind for the player. Capri is the only trigger.
- Production deployment, until the spike passes and you approve it.

## Who can use it

Capri, the companion only. The server checks that the requesting player owns Capri and that she is summoned. The player character cannot trigger it.

## Server gate (authoritative)

Every use request goes through the server, which checks in this order:

1. The player owns Capri.
2. Capri is summoned for that player.
3. The player's cooldown has elapsed.
4. The player can pay the cost.

If any check fails, the server rejects the request and sends a reason code. The client never chooses targets, sets hostility, or changes cooldown or cost.

## Cost and cooldown

- Both are **per player**. One player's use does not block another player.
- Cooldown: **TBD** (starting value 120 s, tunable).
- Cost: **TBD**. The resource and amount must be chosen. Capri's existing resource system needs checking before this is fixed.

## Target sweep

- The server runs a sweep centred on the caster's Capri, radius **40 m**. This matches the existing `TargetSearchQuery` pattern in `Open77ScriptBridge.reds`.
- A per-cast target cap bounds the cost. Starting cap: **1000**, tuned by the spike.
- Each target is classified by type. Only the effects that apply to its type are used (for example, hostility is not applied to a light).

## Target ownership (conflicts)

- A target can be claimed by one Mass Override at a time.
- If a second cast's sweep reaches a claimed target, it skips that target until the claim expires.
- Claims are recorded on the server.

## Effects and duration

- Duration: **30 s** default, configurable on the server.
- The server starts a timer for each cast. When it fires, the server reverts hostility and sends an end event.
- Dismissing Capri does not end the effect early. (Change this only if you ask for it.)
- Hostility is set on the server so NPC behaviour matches for every player. Visual effects (blink, screen change) are sent as one event and applied on each client.

## Broadcast

- One event per cast, containing: caster, target IDs and types, effect, and end time.
- Clients apply visual changes from that event. They do not decide which targets are affected.

## Where it lives

- Trigger, gate, sweep, claims, timers and hostility: server-side, in `opx_infinity` (the server script layer). **TBD**: confirm the exact file layout against the shipped Capri 1.16.3 build before writing code, because the `tmp/preflight-1163b` copies have not been confirmed as current.
- Visual effects: client-side, driven by the broadcast event.

## Phases and gates

**Phase 1: Staging spike (no production changes).** Deploy to `/opt/open77-xbuniverse-staging` (port 11841) only, after your go-ahead.
Measure the sweep and effects at 100, 500 and 1000 targets, and report the cost per tick. Check that one hostile change and one blink reach a second client, and that claims stay consistent across two players.
Go/no-go: proceed only if the 1000-target sweep stays within a tick budget that the spike sets. If it does not, reduce the cap or radius and re-measure.

**Phase 2: single-player-safe client MVP** (the same server path with one player).

**Phase 3: multiplayer.** Two-player test: claims, cooldowns, and revert.

**Phase 4: vehicles.** Hostile behaviour and visual effects on cars, bikes and motorcycles.

**Phase 5: pedestrians and polish.**

Each phase is reviewed before the next starts.

## Open items (TBD)

1. Cooldown value.
2. Cost resource and amount.
3. Exact server file layout, confirmed against Capri 1.16.3.
4. Whether lights, billboards and vehicles can each be driven from script. Not yet verified.
5. Per-tick cost at 1000 targets. Not yet measured.

## Verified engine calls (vanilla tools/redmod/scripts)
- Hostility: `AttitudeAgent.SetAttitudeGroup('HostileToEveryone')`, `AttitudeAgent.SetAttitudeTowards(target, EAIAttitude.AIA_Hostile)`, `GameObject.ChangeAttitudeToHostile(owner, target)` (aiActionHelper.script ~249-400).
- Billboard screen/lights: `BillboardDevice` TurnOnScreen/TurnOffScreen → `m_advUiComponent.Toggle(bool)` and `ToggleLightEvent{toggle, loop}` / `AdvanceChangeLightEvent{settings, time, curve, loop}` (billboard.script, gameLightComponent.script, electricLight.script).
- Vehicles: `VehicleComponent` (vehicleComponent.script); horn hook in Open77ScriptBridge.reds ~206.
- Still unverified: screen content change (AdvertisementWidgetComponent not located in vanilla scripts), vehicle-specific hostility (engine-side, no script found), sweep cost at 1000 targets.

## Decisions from source review
- Vehicles: vanilla vehicleComponent.script only reads hostility (`GetAttitudeTowards == AIA_Hostile`) and never sets it. Use the same AttitudeAgent path for vehicle drivers; in-game effect unverified.
- Screens: AdvertisementWidgetComponent has only `Toggle(bool)` in vanilla (billboard.script, vendingMachine.script). No content setter found, so v1 changes screen on/off plus lights. Changing screen content is out of v1 scope.

## Local bridge (not compiled or run in-game)
- `r6/scripts/Open77/Open77MassOverride.reds` (game install, local only): sweep (`TargetSearchQuery`, 40 m, same filter as Open77ScriptBridge), NPC hostility via `AttitudeAgent.SetAttitudeTowards` (AIA_Hostile / AIA_Neutral, both confirmed in vanilla).
- Wired: `mass_override` is a Capri action (`Capri.Actions.reds`), implemented in `Capri.MassOverride.reds`, with `CapriSystem.Shown()` and `CapriStorage.massOverrideLastAt`.
- Compiled: a scratch REDmod deploy (copy outside the game, real cache untouched) passed script compilation with the new files included. Only vanilla `minimapMappins.script` warnings appeared.
- NPC hostility is the only effect implemented. Lights and screen toggles are NOT implemented: no verified toggle API exists in the shipped scripts (`ToggleLightEvent` not found; `AdvertisementWidgetComponent` has no `Toggle` method in the Codeware dump). Vehicle hostility is unverified.
- Not run in-game yet. Next: one local in-game cast, then measure the sweep at 100/500/1000 targets.
