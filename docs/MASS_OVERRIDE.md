# Mass Override: design

Status: implemented locally, not run in-game. Items marked **TBD** still need a decision.

## Summary

Mass Override is a Capri-only quickhack. Capri, the companion, triggers it from her own action code. It affects many people, screens, lights and vehicles at once, in multiplayer from v1. It has no time dilation, and it does not use the Sandevistan code or dependency.

## Scope

In:
- Targets: NPCs, lights, billboards, TVs and screens, traffic lights, cars, bikes and motorcycles.
- Effects: people turn hostile; every screen and light the probes reach goes dark, including vehicle headlights and traffic lights.
- Multiplayer from v1, server-authoritative.

Out:
- Time dilation of any kind.
- Any item, slot or keybind for the player. Capri is the only trigger.
- Screen content changes (vanilla has no content setter; see "Verified engine calls").
- Production deployment, until the local run passes and you approve it.

## Who can use it

Capri, the companion only. The server checks that the requesting player owns Capri and that she is summoned. The player character cannot trigger it.

## Server gate (authoritative)

Every use request goes through the server, which checks in this order:

1. The player owns Capri.
2. Capri is summoned for that player.
3. The player's cooldown has elapsed.
4. The player can pay the cost.

If any check fails, the server rejects the request and sends a reason code. The client never chooses targets, sets hostility, or changes cooldown or cost. The game-side action repeats the same checks (`CapriMassOverride.Run`) so a single-player session behaves the same way, but the server's answer is the one that counts.

## Cost and cooldown

- Both are per player.
- Cooldown: 120 s (`CapriMassOverride.Cooldown`, `DEFAULTS.cooldownMs`).
- Cost: 25 RAM from the memory pool (`CapriMassOverride.ChargeCost`, `DEFAULTS.cost`). Resource and amount are still **TBD**; 25 is a placeholder.

## Probe sweep (multi-probe)

A single query from V reaches 40 m. That cannot see the next street's lamps or the billboards on the far side of a building, so the sweep is a breadth-first fill instead of one sphere:

1. Probe 1 is V, reach 25 m (`MassOverrideProbe.Reach`).
2. Every screen, light or vehicle found becomes the next probe, so the fill walks outward along the devices themselves and follows a street around a corner instead of reaching through walls.
3. People found are targets but never probes, because they move.
4. The fill stops on a probe budget (`MaxProbes`, 64) or the target cap (1000), whichever comes first.
5. Entities are de-duplicated by `EntityID`, so a device reached by two probes is changed once.

Per cast: at most 64 queries and at most 1000 changed entities. That is the number to measure in Phase 2.

## Areas

Every target records the area it stands in (`MassOverrideTarget.area`), and a cast's event carries the distinct set (`event.areas`). Two pieces make up an area:

- A **50 m world cell** from the target's position (`MassOverrideArea.Cell`) — this is what actually distinguishes "this block" from "that block".
- The **player's district** name, read from `PreventionSystem.GetCurrentDistrict()` → `District_Record.EnumName()`.

The district is the player's, not the target's, and that is a hard limit rather than a shortcut: there is no coordinate-to-district lookup on 2.31. District membership is authored as baked trigger volumes, and the engine will only name the district of the entity standing in one. `Open77Districts.reds` records the compiler-probed result for every guessable alternative.

## Target ownership (conflicts)

- A target can be claimed by one Mass Override at a time.
- A second cast's sweep skips claimed targets until the claim expires.
- Claims are per target `EntityID`, so two casts in different cells never collide, and two casts in the same cell cannot double-apply one device.

## Effects and duration

- Duration: 30 s (`CapriMassOverride.Duration`, `DEFAULTS.durationMs`).
- NPCs: `AttitudeAgent.SetAttitudeTowards(AIA_Hostile)`, reverted to `AIA_Neutral`.
- Screens, billboards, TVs, lights, traffic lights and vehicle lights: the entity's widget and light components are switched off, then switched back on at revert.
- Revert runs on the delay system (`MassOverrideRevert extends DelayCallback`), so dismissing Capri does not end the effect early.
- A device that was already off before the cast is switched on by the revert. Tracking each component's prior state is **TBD**.

## What the probes cannot reach

- **Lighting baked into sector geometry.** A light that is not an entity component cannot be reached from script at all. `cityLightSystem` only exposes read-side state (`GetLightsCount`, `GetFusesCount`, `GetFuseStateByID`, `GetState`), with no public switch, so there is no city-wide light kill in the shipped API.
- **Prefab-embedded lights** that are not separate entities. Devices (`ElectricLight`, `BlindinLight`, `TrafficLight`, `DestructibleMasterLight`) are entities and are reached.
- Probes do not cross a gap with no devices in it: a fill that starts in an alley with no emitters stops there. The probe budget also ends a fill early in a dense district.

## Broadcast

- One event per cast: caster, target IDs and types, areas reached, effect, end time.
- Clients apply the visual result of that event; they do not choose targets.

## Where it lives

- Game side (this repo, `game/r6/scripts`): `Open77/Open77MassOverride.reds` (probes, areas, effects, revert), `CapriPersonalityConstruct/Capri.MassOverride.reds` (the action, cost, cooldown, revert scheduling).
- Server side (`mass-override/`): `gate.js` (owner, summoned, cooldown, cost, claims, cap, area summary), `engine-adapter.js` (applies effects through an adapter and schedules the revert), `dev-server.js`.

## Deploying the scripts

The server compile failed because only `Capri.MassOverride.reds` was synced. It calls three things that live in other files:

| File | Needs |
| --- | --- |
| `Capri.System.reds` | `public func MassOverrideShown() -> Bool { return this.m_presence.Shown(); }` |
| `Capri.Storage.reds` | `public let massOverrideLastAt: Float;` |
| `Capri.Actions.reds` | `case "mass_override": return CapriMassOverride.Run(player, CapriSystem.Get(player.GetGame()));` |

Copy all four files from the same build, or run `mass-override/sync-scripts.sh "<path to Cyberpunk 2077>"`, which copies the two owned files and checks the three edits above, failing loudly when one is missing.

## Phases and gates

**Phase 1: local.** One cast in a local session. Pass: people turn hostile and screens, lights, billboards and vehicle lights go dark, and everything is back to normal after 30 s.

**Phase 2: measure.** Probe count, target count and frame cost at 100, 500 and 1000 targets. If the fill is too expensive, lower `MaxProbes` first, then the cap; do not drop target types to make the numbers look better.

**Phase 3: multiplayer.** Two-player test: claims, cooldowns, revert, and one cast reaching the other client, including two casts in different areas at once.

Each phase is reviewed before the next starts.

## Verified engine calls

Read from the source that ships with REDmod (`tools/redmod/scripts`), not guessed:

- Hostility: `AttitudeAgent.SetAttitudeTowards(EAIAttitude.AIA_Hostile)` — already used by `Open77PlayerModels.reds`.
- Billboards: `BillboardDevice` ends `TurnOffScreen`/`TurnOnScreen` in `m_advUiComponent.Toggle(bool)` (billboard.script).
- TVs: `TV.TurnOffScreen`/`TurnOnScreen` end in `m_uiComponent.Toggle(bool)` (tv.script).
- LCD screens: the same `Toggle(bool)` (lcdScreen.script).
- Lights: `ElectricLight` requests `gameLightComponent` for its sources; `vehicleLightComponent` derives from `gameLightComponent` (Codeware RTTI).
- Traffic lights: red, yellow and green are light components on the device, selected by `ToggleLightByNameEvent` (trafficLight.script), so the light-component switch covers them.
- Warning/search lights: `BlindingLight` and `DestructibleMasterLight` are devices whose `TurnOffDevice` ends in their own light toggle; they are reached as entities.
- Widget component names differ per device (`ui`, `ads`, `tv_ui`, `radio_ui`, `terminalui`), so components are selected by class, not by name.
- `Entity.GetComponents()`, `IComponent.IsEnabled()`, `IComponent.Toggle(bool)`, `ArrayContains`, `RoundF`, `ToString` and `DelayCallback` are all used elsewhere in this project already.

Not available to redscript, which is why the component switch is used instead:
- `ToggleLightEvent`, `ToggleLightByNameEvent` and the light classes are not in the redscript RTTI dump.
- There is no spatial-query system in the RTTI, so probes go through `TargetingSystem.GetTargetParts` from a real entity.

Still unverified:
- Screen content changes (no content setter exists in vanilla; out of scope).
- Vehicle-specific hostility (vanilla only reads vehicle attitude; drivers are ordinary NPCs and are handled by the NPC path).
- Real probe coverage and per-cast cost at 1000 targets.

## Verification status

- Node tests: `node --test mass-override/gate.test.js mass-override/engine-adapter.test.js` — 14/14 pass (8 gate, 6 engine layer), including the area summary and screens, billboards, lights and vehicles going dark and reverting.
- Game scripts: the redscript build that included the previous version of these files compiled with 0 errors (603 warnings, none in these files). The current version has NOT been compiled: `scc.exe` only accepts `.script`, and the game needs Steam running before redscript runs at startup.
- Not run in-game. Coverage, visuals and frame cost are unconfirmed.

## Open items

1. Cooldown value (120 s placeholder).
2. Cost resource and amount (25 RAM placeholder).
3. Probe budget and reach: 64 × 25 m is a starting point, not a measurement.
4. Whether component toggling is enough for every light type, or some need `ToggleLight`.
5. Whether the revert should restore a device that was already off.
6. Whether areas should be persisted across casts, so a second flood in the same block skips probing.
