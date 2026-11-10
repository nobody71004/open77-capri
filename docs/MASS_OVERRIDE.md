# Mass Override: design

Status: implemented locally, not run in-game. Items marked **TBD** still need a decision.

## Summary

Mass Override is a Capri-only quickhack. Capri, the companion, triggers it from her own action code. It affects many people, screens, lights and vehicles at once, in multiplayer from v1. It has no time dilation, and it does not use the Sandevistan code or dependency.

## Scope

In:
- Targets: NPCs, lights, billboards, TVs and screens, cars, bikes and motorcycles.
- Effects: people turn hostile; every screen and light in range goes dark, including vehicle lights.
- Multiplayer from v1, server-authoritative.

Out:
- Time dilation of any kind.
- Pedestrians below the target cap behave like any other NPC; there is no separate pedestrian pass.
- Any item, slot or keybind for the player. Capri is the only trigger.
- Production deployment, until the local run passes and you approve it.

## Who can use it

Capri, the companion only. The server checks that the requesting player owns Capri and that she is summoned. The player character cannot trigger it.

## Server gate (authoritative)

Every use request goes through the server, which checks in this order:

1. The player owns Capri.
2. Capri is summoned for that player.
3. The player's cooldown has elapsed.
4. The player can pay the cost.

If any check fails, the server rejects the request and sends a reason code. The client never chooses targets, sets hostility, or changes cooldown or cost.

The game-side action repeats the same checks (`CapriMassOverride.Run`) so a single-player session behaves the same way, but the server's answer is the one that counts.

## Cost and cooldown

- Both are per player. One player's use does not block another's.
- Cooldown: 120 s, tunable (`CapriMassOverride.Cooldown`, `DEFAULTS.cooldownMs`).
- Cost: 25 RAM from the memory pool (`CapriMassOverride.ChargeCost`, `DEFAULTS.cost`). The resource and amount are still **TBD**; 25 is a placeholder.

## Target sweep

- Centred on the caster (Capri), radius 40 m, the same `TargetSearchQuery` pattern as `Open77ScriptBridge.reds`.
- Per-cast cap: 1000 targets.
- Each target is classified as `npc` (kind 0) or `device` (kind 1). Anything with a world widget or a light component is a device; everything else is ignored, so the cap is not spent on props.

## Target ownership (conflicts)

- A target can be claimed by one Mass Override at a time.
- A second cast's sweep skips claimed targets until the claim expires.

## Effects and duration

- Duration: 30 s (`CapriMassOverride.Duration`, `DEFAULTS.durationMs`).
- NPCs: `AttitudeAgent.SetAttitudeTowards(AIA_Hostile)`, reverted to `AIA_Neutral`.
- Screens, billboards, TVs, lights and vehicle lights: the entity's widget and light components are switched off, then switched back on at revert.
- Revert runs on the delay system (`MassOverrideRevert extends DelayCallback`), so dismissing Capri does not end the effect early.
- A device that was already off before the cast is switched on by the revert. Tracking each component's prior state is **TBD** if that turns out to matter.

## Broadcast

- One event per cast: caster, target IDs and types, effect, end time.
- Clients apply the visual result of that event; they do not choose targets.

## Where it lives

- Game side (this repo, `game/r6/scripts`): `Open77/Open77MassOverride.reds` (sweep and effects), `CapriPersonalityConstruct/Capri.MassOverride.reds` (the action, cost, cooldown, revert scheduling).
- Server side (`mass-override/`): `gate.js` (owner, summoned, cooldown, cost, claims, cap), `engine-adapter.js` (applies effects through an adapter and schedules the revert), `dev-server.js`.

## Deploying the scripts

The server compile failed because only `Capri.MassOverride.reds` was synced. It calls three things that live in other files:

| File | Needs |
| --- | --- |
| `Capri.System.reds` | `public func MassOverrideShown() -> Bool { return this.m_presence.Shown(); }` |
| `Capri.Storage.reds` | `public let massOverrideLastAt: Float;` |
| `Capri.Actions.reds` | `case "mass_override": return CapriMassOverride.Run(player, CapriSystem.Get(player.GetGame()));` |

Copy all four files from the same build, or run `mass-override/sync-scripts.sh "<path to Cyberpunk 2077>"`, which copies the two owned files and checks the three edits above, failing loudly when one is missing.

## Phases and gates

**Phase 1: local.** One cast in a local session. Pass: people turn hostile and screens, lights, billboards and vehicle lights go dark, all on screen, and everything is back to normal after 30 s.

**Phase 2: measure.** Sweep and effects at 100, 500 and 1000 targets. If 1000 exceeds a frame budget, reduce the cap or radius rather than the target types.

**Phase 3: multiplayer.** Two-player test: claims, cooldowns and revert, plus one cast reaching the other client.

Each phase is reviewed before the next starts.

## Verified engine calls

Read from the source that ships with REDmod (`tools/redmod/scripts`), not guessed:

- Hostility: `AttitudeAgent.SetAttitudeTowards(EAIAttitude.AIA_Hostile)` — already used by `Open77PlayerModels.reds`.
- Billboards: `BillboardDevice` ends `TurnOffScreen`/`TurnOnScreen` in `m_advUiComponent.Toggle(bool)` (billboard.script).
- TVs: `TV.TurnOffScreen`/`TurnOnScreen` end in `m_uiComponent.Toggle(bool)` (tv.script).
- LCD screens: same `Toggle(bool)` (lcdScreen.script).
- Lights: `ElectricLight` requests `gameLightComponent` for its sources; `vehicleLightComponent` derives from `gameLightComponent` (Codeware RTTI).
- Widget component names differ per device (`ui`, `ads`, `tv_ui`, `radio_ui`, `terminalui`), so components are selected by class, not by name.
- `Entity.GetComponents()`, `IComponent.IsEnabled()`, `IComponent.Toggle(bool)` and `DelayCallback` are all used elsewhere in this project already.

Not available to redscript, which is why the component switch is used instead:
- `ToggleLightEvent` and the light classes are not in the redscript RTTI dump.

Still unverified:
- Screen content changes (no content setter exists in vanilla; out of scope).
- Vehicle-specific hostility (vanilla only reads vehicle attitude; drivers are ordinary NPCs and are handled by the NPC path).
- Per-tick cost at 1000 targets.

## Verification status

- Node tests: `node --test mass-override/gate.test.js mass-override/engine-adapter.test.js` — 12/12 pass, including screens, billboards, lights and vehicles going dark and reverting.
- Game scripts: the redscript build that included the previous version of these files compiled with 0 errors (603 warnings, none in these files). The current version has NOT been compiled: `scc.exe` only accepts `.script`, and the game itself needs Steam running before redscript runs at startup.
- Not run in-game. Nothing here is confirmed to look right on screen.

## Open items

1. Cooldown value (120 s placeholder).
2. Cost resource and amount (25 RAM placeholder).
3. Per-tick cost at 1000 targets.
4. Whether component toggling is enough for every light type, or some need `ToggleLight`.
5. Whether the revert should restore a device that was already off.
