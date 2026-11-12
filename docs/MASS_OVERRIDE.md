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

- Both are per player, and both are enforced by the server gate (`DEFAULTS.cooldownMs`, `DEFAULTS.cost`). The game-side action deliberately keeps no cooldown of its own: that would need a storage field the stock Capri build does not have, and the request is admitted by the server anyway.
- Cooldown: 120 s (`DEFAULTS.cooldownMs`).
- Cost: 25 RAM from the memory pool, spent locally by the action (`CapriMassOverride.ChargeCost`) and checked against the server balance. Resource and amount are still **TBD**.

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

## Area cache

A fill is up to 64 targeting queries, so its result is remembered per area (`MassOverrideCache`). The cache is a redscript service, looked up the way Capri's own storage service is (`GameInstance.GetScriptableServiceContainer().GetService(n"MassOverrideCache")`); if the container ever returns null, `Get()` returns null and the sweep probes every time, so the cache can only ever be a saving.

- **Devices are cached**, capped at the 1000 target limit, for up to 8 areas (oldest dropped first).
- **People are never cached.** They move, so a cache hit still runs `Fill(player, cap, false)`: one query from V for the people around V, and nothing else. A repeated flood in a known block therefore costs one query instead of up to 64.
- **A hit only changes what is still there.** Every cached entry is re-checked as it is read: the entity must still exist, still have a switchable widget or light component, and still be standing in the cell it was cached in. Anything that fails is dropped from the entry, which is how a destroyed billboard or a car that drove off stops being a target.
- The cache lives for the session. It is not saved, so a reload starts with an empty one.

One consequence: on a cache hit, people are gathered only around V, because the devices that would have carried the fill further down the street are not probed again. In a known block the second flood turns fewer distant people than the first.

## Instrumentation

`FTLog` is this project's log call (Capri uses it throughout), and `EngineTime.ToFloat(GameInstance.GetSimTime(game))` is the clock. Every cast logs one line:

```
[MassOverride] mode=blink modeSource=local pin=none cost=25 ram=38 area=Watson:12:-3 cache=miss blocks=1 probes=12 parts=931
  people=142 devices=812 changed=940 targets=954 cap=1000 secs=0.000
```

What each field means when you are chasing the 100 / 500 / 1000 target numbers:

- `mode` — the mode this cast ran, `blink` or `blackout`. `modeSource` says who picked it: `server` when a broadcast supplied it, `local` when the pin, the cursor or the clock did. `pin` says whether a pin is in force (`none` while casts alternate), so `mode=blink pin=none` is an alternating cast and `mode=blink pin=blink` one a pin chose — the pair is what tells the two apart in a session log.
- `cost` / `ram` — what the cast charged out of the RAM pool and the pool value read just before the charge. The deduction is a stat-pool request, so `ram` is the pre-charge figure and the next cast's value shows what the last one took. `cost=0` means Capri is set not to use RAM, so the cast is free rather than quietly charging anyway.
- `probes` — targeting queries issued. 1 on a cache hit, up to `MaxProbes` (64) on a miss. This is the number that decides whether the fill is affordable.
- `parts` — target parts those queries returned, i.e. everything the targeting system looked at before filtering.
- `devices` / `people` — what survived the filter and became targets.
- `changed` — components actually switched by the first pass. Screens have several widgets, so this exceeds `devices`.
- `lightStates` — lights whose own on/off state (`ToggleLight`) was switched. This is the path that should be doing the work.
- `lightFallbacks` — lights that only the component switch could move, i.e. the fallback carrying them because their state did not change.
- `lightEvents` — entities a `ToggleLightEvent` was queued to (once per entity that has a light, not once per light).

Those three are what answer "which path is actually working". `lightStates` high and `lightFallbacks` near zero means the light state and the entity event are doing it. `lightFallbacks` tracking or exceeding `lightStates` means `ToggleLight` is not moving those lights and the component disable is carrying the blackout — and if the street still comes back on, that fallback is being undone by the device controller. `lightEvents` counts only what was queued, never whether the receiving controller honoured it, which is the part no script can observe.
- `targets` — size of the list handed to the effect, i.e. what the cap applied to. `targets` near `cap` means the cap, not the block, is the limit.
- `cache` / `blocks` — whether the devices came from the area cache and how many areas it holds.
- `services` — which service name actually registered, or `none`. `cache=MassOverrideCache prefs=MassOverridePrefs` is healthy; `Open77.` prefixed names mean the module-qualified spelling is the one being served; `none` means that service did not register, and a separate `[MassOverride] service missing:` line is then logged on the same cast so it cannot be missed. This is the field that distinguishes "the mode never changes" from "the mode service never loaded", and "the cache never hits" from "the cache service is absent".

The separate `service missing:` line is printed **once per session**, not once per cast. Redscript has no static fields, so the flag lives in whichever of the two services did register — the first missing service is therefore reported exactly once. If neither registered there is nowhere to keep the flag, and the warning is limited to the first second of each hour of sim time instead, which keeps it visible without a line per cast.
- `secs` — the cast measured outside the work. A fill runs inside one frame, so sim time usually does not advance within it and this can honestly read `0.000`. Treat the counts as the measurement and this as a sanity check.

To read the three data points, cast in a quiet block (`targets` around 100), a busy one (around 500) and a dense one such as a market street at night (around 1000), and read `probes` against `targets` in each line. `Instrumented()` returns false to silence the line.

## Target ownership (conflicts)

- A target can be claimed by one Mass Override at a time.
- A second cast's sweep skips claimed targets until the claim expires.
- Claims are per target `EntityID`, so two casts in different cells never collide, and two casts in the same cell cannot double-apply one device.

## Modes

Two modes, both kept:

- **Blink** (default, `MassOverrideMode.Blink`). Lights and screens strobe for the whole duration: one pulse per second, each pulse re-armed on the delay system (`MassOverridePulse`), then the block ends lit. Reads as an overload rather than a power cut.
- **Blackout** (`MassOverrideMode.Blackout`). Everything goes dark at once and stays dark for the duration, then restores. Reads as a power cut, which is a different beat in a chase.

NPCs turn hostile in both modes; the mode only changes what happens to screens and lights.

Which one Capri gets: `CapriMassOverride.Mode()` asks `MassOverridePrefs`, which hands out one mode per cast, starting with blackout and flipping each time; `Pin()` fixes one and `Auto()` resumes alternating. `RunWith(player, system, mode)` is the explicit door for a per-action choice later, without changing `Run`'s signature that `Capri.Actions.reds` calls. The server gate carries the same policy (see "The gate mirrors it" below).

## Effects and duration

- Duration: 30 s (`CapriMassOverride.Duration`, `DEFAULTS.durationMs`).
- NPCs: `AttitudeAgent.SetAttitudeTowards(AIA_Hostile)`, reverted to `AIA_Neutral`.
- Screens, billboards, TVs, lights, traffic lights and vehicle lights: the entity's widget and light components are switched, then switched back on at revert.
- Revert runs on the delay system (`MassOverrideRevert extends DelayCallback`), so dismissing Capri does not end the effect early.
- A device that was already off before the cast is switched on by the revert. Tracking each component's prior state is **TBD**.

## What the probes cannot reach

- **Lighting baked into sector geometry.** A light that is not an entity component cannot be reached from script at all. `cityLightSystem` only exposes read-side state (`GetLightsCount`, `GetFusesCount`, `GetFuseStateByID`, `GetState`), with no public switch, so there is no city-wide light kill in the shipped API.
- **Prefab-embedded lights** that are not separate entities. Devices (`ElectricLight`, `BlindinLight`, `TrafficLight`, `DestructibleMasterLight`) are entities and are reached.
- Probes do not cross a gap with no devices in it: a fill that starts in an alley with no emitters stops there. The probe budget also ends a fill early in a dense district.

## Broadcast

- One event per cast: caster, target IDs and types, areas reached, mode (`blink` or `blackout`), end time.
- Clients apply the visual result of that event; they do not choose targets.

## Where it lives

- Game side (this repo, `game/r6/scripts`): `Open77/Open77MassOverride.reds` (probes, areas, effects, revert), `CapriPersonalityConstruct/Capri.MassOverride.reds` (the action, cost, cooldown, revert scheduling).
- Server side (`mass-override/`): `gate.js` (owner, summoned, cooldown, cost, claims, cap, area summary), `engine-adapter.js` (applies effects through an adapter and schedules the revert), `dev-server.js`.

## Deploying the scripts

Two files, and both have to travel together in the launcher package:

- `r6/scripts/Open77/Open77MassOverride.reds` (probes, effects, prefs, cache, the cast/feed HTTP classes)
- `r6/scripts/CapriPersonalityConstruct/Capri.MassOverride.reds` (the action, cost, cooldown, scheduling)

`Capri.MassOverride.reds` calls `MassOverrideProbe`, `MassOverridePrefs`, `MassOverrideEffects` and
`MassOverrideCastPost`, which are declared in the Open77 file. The official Capri release does not
contain that file and no other launcher package ships it, so a package built without it leaves every
player with a script set that fails to resolve. `scripts/build_capri_launcher_mod.py` adds it from this
repo automatically (`Mass Override: added r6/scripts/Open77/Open77MassOverride.reds`).

### Reply handlers must be `cb` **and** must outlive their request

Both HTTP reply handlers (`MassOverrideFeedPoll.OnReply` and `MassOverrideCastPost.OnReply`) are
declared `cb func`. RedHttpClient stores the target as a weak reference and invokes the named method;
a method without `cb` is never invoked and the response is dropped silently. That failure looked like
Mass Override doing nothing: the register request was answered but the cast that follows the reply was
never sent, and the feed poller never re-armed (one feed request per session in
`red4ext/logs/redhttpclient-*.log`). `HttpCallback.target` is a `wref<IScriptable>`, so the reply only lands while the target is alive. A
one-shot `DelayCallback` is released the moment its `Call()` returns, which killed both objects before
their replies arrived. Both now keep themselves scheduled across the request: the feed poll re-arms
`this` before it sends (also making it the permanent poller, guarded by `MassOverridePrefs.FeedRunning()`),
and the cast post schedules `this` for `KeepAliveSeconds()` and returns early when that keep-alive fires.
This is the same mechanism that keeps the pulse/hold/revert callbacks alive.

`mass-override/reds-lint.test.js` asserts the `cb` keyword and both self re-arms.

### Runtime diagnostics

`FTLog` output does not reach a readable log in every install. Each stage of a cast is appended to
`r6/storages/CapriConstruct/mass_override.log` as well (`MassOverrideLog`): cast entered, guards
(recharge, charge, empty sweep), probe counts, register/cast replies, and the final `mode=...` line with
`hostile=` and `changed=`. One line per stage means a cast that stops early says where it stopped.

`Capri.Actions.reds` must carry `case "mass_override": return CapriMassOverride.Run(player, CapriSystem.Get(player.GetGame()));`. If Capri reaches the action at all, that line is already there.

No other Capri file needs editing. An earlier version of this action called `CapriSystem.MassOverrideShown()` and read `CapriStorage.massOverrideLastAt`, so it only compiled once matching edits in `Capri.System.reds` and `Capri.Storage.reds` had been synced as well. Twice they had not, and the whole script set failed with `UNRESOLVED_MEMBER`. The action now references no Capri member beyond the stock build, so that class of failure cannot happen again. `CapriMassOverride.Duration`, `ChargeCost` and `Cap` are all local constants.

Run `mass-override/sync-scripts.sh "<path to Cyberpunk 2077>"` to copy both files and check the action case.

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
- Billboards: vanilla `billboard.script` asks for `'AdvertisementWidgetComponent'` on its `ui` slot and switches it with `m_advUiComponent.Toggle(false)`. In the 2.31 RTTI table that class extends `IWorldWidgetComponent`, so the same screen test catches billboards, LCD screens, TVs and vending-machine ads.
- Vehicles: `vehicleLightComponent` extends `gameLightComponent`, so headlights, brake lights and interior lights are switched by the light rule. Cars are also classified as their own kind so the log reports how many were reached.

### Evidence behind those types

The RTTI table the Red4ext plugin ships (`red4ext/plugins/Open77/rtti-manifest-2.31.json`) is the engine's own list of types a script may name, and it settles each one:

| Name | Kind | Parent | Note |
| --- | --- | --- | --- |
| `IWorldWidgetComponent` | class, abstract | `WidgetBaseComponent` | screens, billboards, TVs |
| `AdvertisementWidgetComponent` | class | `IWorldWidgetComponent` | billboards, vending ads |
| `gameLightComponent` | class | `entLightComponent` | lamps, traffic lights |
| `vehicleLightComponent` | class | `gameLightComponent` | headlights, brake, interior |
| `vehicleBaseObject` | class | `gameObject` | the car entity |
| `ScriptableService` | class, abstract | `IScriptable` | the area cache |

`VehicleObject` is the script-side class Capri already casts to (`Capri.Actions.reds`), so it is safe here too; casting to a name that only exists as an enum value would not compile.

One thing that table does *not* settle: `TSFMV` has no vehicle flag in 2.31 — only `Obj_Puppet`, `Obj_Player`, `Obj_Device`, `Obj_Sensor` and `Obj_Other`. So whether a targeting probe returns a car is unproven on paper, and the `vehicles=` count in a real cast is the test: a non-zero count in traffic means cars are reached, zero on a street full of parked cars means they are not.

### Why blackout did not work

Two faults, both in the mode plumbing:

1. **It was switched once and then overwritten.** A device's own controller keeps its screen and lights in step with its state, so it switches its component back on within a frame or two. The blink survived that because each pulse re-asserts twice a second; the blackout toggled once at the start and was silently undone, which read as nothing happening. Blackout now uses `MassOverrideHold`, which re-asserts dark every second for the whole duration, and the revert lights it back up after.
2. **The mode was being decided by an unrelated setting.** `Mode()` mapped `settings.unleashed` onto blackout. That field is Capri's quickhack-tier setting (`Capri.Storage.reds`: "her quickhacks at their strongest tier"), true by default and off for anyone paying per-target RAM — so blackout was unreachable for anyone who had turned it off, and switched on without being asked for anyone who had not. `Mode()` now reads `MassOverridePrefs` instead, which is Mass Override's own state; `RunWith(player, system, mode)` remains the explicit door.

### How a light is switched now

Screens stay on the component switch, because that is exactly what the vanilla screen classes do (`lcdScreen.TurnOffScreen` is `m_uiComponent.Toggle(false)`). Lights do not work that way. Disabling a light *component* only hides it until a device controller enables the component again — which is what a blackout kept losing to.

So a light is switched by its own state instead. The 2.31 RTTI table lists `gameLightComponent.ToggleLight(on, loop)` and `IsOn()`, so `SetLight` compares `IsOn()` and calls `ToggleLight` only when the state differs. The entity is then also sent the event vanilla's own billboard queues:

```redscript
let evt: ref<ToggleLightEvent> = new ToggleLightEvent();
evt.toggle = on;
evt.loop = false;
target.QueueEvent(evt);
```

Both paths set a desired state rather than flipping one, so running them together is idempotent — the event covers lights that belong to a mesh or a child entity, and `ToggleLight` covers props that never handle the event. Constructing and queueing a vanilla event from redscript is the pattern Capri already uses and compiles with (`target.QueueEvent(new QuickHackExplodeExplosive())`), so this is not a new mechanism.

`SetLight` returning false when `IsOn()` already matches is what makes the blackout hold cheap: each one-second re-assert only touches the lights a device has switched back on.

### What the revert puts back

Each target records two booleans before anything is switched — `screenWasOn` and `lightWasOn` — read in `Fill` during the sweep (which runs before the apply pass) and, for a cache hit, in `Recall` at the moment the cached device is turned back into a target. The revert then restores each part to that state rather than switching everything on:

```redscript
MassOverrideEffects.Switch(object, target.screenWasOn, target.lightWasOn, sink);
```

`Switch` is the same body as `BlinkReported` with the two parts separated, so a newsstand screen that was already dark stays dark, and a lamp that was off before the cast stays off. The blink's final pulse calls `RestoreAll` for the same reason — it used to end "lit", which both ruined a pre-darkened street and, because the pulse count outran the revert, could re-light everything one second *after* the revert had already restored it.

People have no prior state: they are released from hostility, which is a clean yes/no. Because restore compares state before switching, running it twice (final pulse, then revert) is a no-op the second time.

### Picking the mode per cast

The choice lives in Mass Override's own state (`MassOverridePrefs`, a scriptable service in `Open77MassOverride.reds`), because the two obvious surfaces are both closed:

- Capri's settings are her *quickhack tier*, not a visual mode — mapping blackout onto `unleashed` was the bug that made blackout unreachable.
- Her action table (`CapriActions.Run(player, action, out hits)`) does not dispatch to Mass Override at all yet, and adding an action there means editing a Capri file, which is exactly the kind of cross-file reference that broke the whole script set twice.

So the default is **one choice per cast, starting with blackout**: the first cast holds the block dark, the next blinks, the one after holds it dark again. Both modes are reachable per cast with nothing to press and nothing to edit, and blackout needs no edit to test because it is what the first cast does. The preference is kept in the service, so it survives across casts within a session:

```redscript
CapriMassOverride.Pin(MassOverrideMode.Blackout()); // every cast from now on
CapriMassOverride.Pin(MassOverrideMode.Blink());    // back to blink
CapriMassOverride.Auto();                           // alternate again
```

`RunWith(player, system, mode)` still takes a mode explicitly and bypasses the preference entirely, so a future action-table wiring can pass whatever Capri's request asks for without touching this policy.

If the service is unavailable, the mode does not collapse to one value: `Mode(game)` falls through to `ModeFromClock(game)`, which returns blackout on an even second of sim time and blink on an odd one. Both modes stay reachable with nothing registered and nothing to edit — the service only turns that into a clean per-cast alternation instead of a clock-driven one. Two casts inside the same second repeat the mode, so waiting a second flips it. This is why `Mode` takes the game instance: the fallback needs sim time. The log line reports whichever mode actually ran (`mode=blink` / `mode=blackout`), which is the quickest way to confirm the alternation is working, and `pin=none|blink|blackout` beside it says whether a pin chose it: `mode=blink pin=none` is an alternating cast, `mode=blink pin=blink` is a pinned one, so a log can tell a pinned mode from one that merely came up next.

### The gate mirrors it

`mass-override/gate.js` implements the same policy, so a broadcast names the mode the game will actually run:

- `mode: "alternate"` (default) hands out one mode per cast and flips a cursor, starting with `"blackout"` — the same sequence and the same first value as `MassOverridePrefs`.
- `mode: "blink"` or `"blackout"` pins that mode, and `setMode()` switches between pinned and `"alternate"`, the counterpart of `Pin()` and `Auto()`.
- The cursor is shared by the whole session: any player's cast advances it, so the server and every client stay on the same beat. A private per-player cursor would let two players in the same street run opposite modes.
- The game side follows the broadcast: `CapriMassOverride.ReceiveServerMode(mode)` stores the mode named in the cast event, and `Mode()` consumes it before the pin or the local cursor, so a client runs the server's beat for that cast and does not advance its own cursor past everyone else. The mode is held for one cast only, so a cast that never runs locally cannot leak into the next one. With no broadcast — solo, or the multiplayer layer not wired yet — the pin, the cursor and the clock still decide. The cast log line reports `modeSource=server|local`, so which one ran is visible per cast rather than inferred.
  Nothing in `r6/scripts` calls `ReceiveServerMode` yet: the multiplayer layer that receives cast events is not wired to Mass Override, so today every cast logs `modeSource=local`.
- Live control in game: `CapriMassOverride.SetModeFromAction(target)` is the counterpart of `POST /mode`, reached as `{"do":"mass_override_mode","target":"blink"|"blackout"|"auto"}` — `blink` and `blackout` pin every following cast, `auto` (also `alternate`) resumes one mode per cast, and anything else changes nothing. The dispatch case and its prompt line live in `Capri.Actions.reds`, which this repo does not track: `mass-override/sync-scripts.sh` asserts both the cast case and the mode case, so a Capri update that drops them fails the sync instead of leaving a control that silently does nothing.
- The dev server exposes the same switch as `POST /mode` with `{ "mode": "blink" | "blackout" | "alternate" }`, so a pin can be flipped without restarting it; anything else is refused with 400 and `GET /state` reports the mode currently in force.

Pinning never consumes the cursor, so going back to `"alternate"` resumes from wherever the alternation left off rather than restarting. `gate.test.js` covers the sequence, the per-player cursors and the pin/unpin round trip.
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

## 1.16.11: levers the game itself uses

The first live cast that produced a report (1.16.10, staging, Japantown, 2026-11-11) ran to the end and changed nothing anyone could see:

```
{"mode":"blackout","probes":62,"parts":128,"people":11,"hostile":11,"devices":50,"screens":31,"lights":12,"vehicles":7,"changed":243,"lightEvents":49}
```

The `/cast` candidates said why. The 31 "screens" were vending machines, door lock panels, a gate and a computer; the 12 "lights" were traffic and crosswalk lights, one reflector and loot crates. Not one TV, billboard, sign or street lamp, because `GetTargetParts` only returns entities with a targeting component. And the effect on those it did find was a disabled widget or light component, which is not what makes a street bright; the people only had an attitude flag set.

1.16.11 keeps the probe and replaces every effect with a switch the game itself uses. All of them were read in the REDmod script sources that ship with the game (`tools/redmod/scripts`) and checked with the game's own compiler.

| What | How | Source it copies |
| --- | --- | --- |
| City lights | `ForceCLSStateRequest` (ForcedOFF, source `CapriMassOverride`, priority VeryHigh, `savable = false`) to `CityLightSystem`; the revert sends DEFAULT for the same source, which removes only that entry. Blink alternates ForcedOFF / ForcedON every 0.5 s. | `core/systems/cityLightSystem.script` (the rain listener and quests use the same request) |
| Devices | `ExecutePSAction(ActionSetDeviceUnpowered())` on the device's own controller; the revert sends `ActionSetDevicePowered()`, which restores the state the controller cached. Only visual device classes: vending machines, TVs, LCD screens, billboards, ads, signs, arcade machines, jukeboxes, radios, speakers, electric lights, reflectors, traffic lights. Doors, gates, terminals, cameras, turrets, loot and traps are reported (`powerSkipped`) and left alone. | `scriptableDeviceBasePS.script` (`UnpowerDevice` / `PowerDevice`), `deviceBase.script` (`CutPower` / `RestorePower`) |
| Traffic lights | The cut, plus a `ToggleLightEvent(false)` every 0.25 s during a blackout: the traffic system's colour change re-lights the bulbs without checking the device state. | `trafficLight.script` (`OnTrafficLightChangeEvent`, `TurnOffLights`) |
| People | `StimBroadcasterComponent.BroadcastStim(player, Terror, 60 m)` at the cast and every 6 s, plus `SendStimDirectly(Terror)` to every person the probe found; the attitude switch is kept. | `psychoSquadAVSystem.script` (MaxTac's arrival) |
| Cars | Empty, parked, non-player cars: `vehicleControllerPS.SetAlarm(true)` (added to `VehicleComponentPS` as `CapriMassOverrideCarAlarm`), off at the revert. Not the `ForceCarAlarm` action: its off-timer is the quickhack upload time, 0 outside a quickhack. Occupied cars honk (`VehicleQuestHornEvent`, 3 s). | `vehicleComponentPS.script` (`OnForceCarAlarm`) |
| Unreachable devices | `MassOverrideRegistry` (a ScriptableSystem) registers Codeware `Entity/Attach` and `Entity/Detach` callbacks for the classes above and keeps the attached ones in an `inkHashMap` keyed by entity id; each cast adds those within 70 m that the probe did not find. | Codeware 1.21 `CallbackSystem`, `EntityTarget.Type` |

Nothing touches components directly any more: a light component disabled from outside stays dark even after its device turns it back on, so the device's controller does both the off and the on.

### 1.16.12 and the brain

The first cast on 1.16.11 never reached the game's action code. Capri Brain forwarded the model's reply untouched because it was not JSON at all - `"actions":["mass_override","target":"North Oak"]` (the prompt's own `{"do":"mass_override","target":...}` line invites the target) - so `forceMassOverride` could not parse it and gave up, Capri dropped the action, and with no cast there was no report. The request also waited 42 s for the model (qwen2.5:7b on CPU).

- `client/mcp/capri-brain.mjs`: a request whose utterance clearly asks for Mass Override is now answered by the brain itself, without a model call, in the same completion shape: `{"say":"Mass Override, V.","actions":[{"do":"mass_override"}]}`, plus `mass_override_mode` first when the utterance names blink, blackout or auto. The utterance is the `V says:` line of the SITUATION block when the game sends one (that block also quotes older events, which must not count). Only for a client whose system prompt lists `"do":"mass_override"`, so a Capri build without the action is never sent one. `CAPRI_BRAIN_MO_SHORTCUT=0` turns it off; the fallback then replaces a non-JSON reply whole instead of giving up. Answered in 10 ms on the server.
- 1.16.12: a sweep that finds nothing no longer returns early. The city lights and the panic need no target, and the early return also skipped every report, which looked exactly like the action never running. The registry's reach is 120 m (a billboard across the street is often 80-120 m away), wider than the probe's 70 m.

### 1.16.13: what the tests showed, and seeing it ourselves

Four live casts on 2026-11-11 and what each one proved:

| Cast | Where / when | Reported | What V saw |
| --- | --- | --- | --- |
| 1.16.10 | Japantown | 243 component toggles on vending machines, door panels, traffic lights | nothing |
| 1.16.11 | North Oak, 08:52 | never ran: the model's reply was not JSON (fixed in the brain) | nothing |
| 1.16.12 | XYBERCITY hub, North Oak, 01:00 | 20 devices cut, 19 still cut 2 s later, screens and lights off | nothing: the screens, signs and people in view were custom content and players, not game devices or crowd |
| 1.16.12 | Japantown, 08:52 | 101 devices cut (15 vending machines, 35 traffic/crosswalk lights, 35 street lamps, 15 TVs), 92 still dark at 2 s, 1 car alarm, 7 horns, 8 panic stims | people ran; no visible change to lights, screens or cars |

The two casts after that one (74 s and 107 s later, then 71 s later) were refused by the 120 s recharge, which only went into Capri's hidden transcript (`Note`). 1.16.13:

- **On-screen confirmation**: `CapriSystem.Alert` after every cast (city lights, devices cut and how many were in view, how many people can panic, car alarms) and when a cast is refused (recharging, battery). Before this a cast that ran and one that never happened looked the same.
- **Recharge 40 s** on both sides (`CapriMassOverride.Cooldown()`, gate `cooldownMs`): the 30 s effect, its revert and a margin. Still a placeholder.
- **The revert reaches devices that streamed out**: the cut keeps the device's controller on the target (`target.ps`) and the power comes back through it. The 1.16.12 North Oak cast was followed by a fast travel and its revert restored 0 of 20; the Japantown one restored 37 of 92, the rest had streamed out while V walked.
- **Pictures**: Capri Voz (the helper that already takes Capri's screenshots, `vista_pedido.json` / `vista_respuesta.json`) is asked for one 3 s and 15 s into the effect and one after the revert; the picture Capri took when V asked is kept as "before". Each is saved as base64 text in `r6/storages/CapriConstruct/mass_override_<cast>_<phase>.b64`; nothing is uploaded.
- **Report fields**: `litBefore` (cut devices that had a screen or light on), `cutInView` (cut devices in the camera frustum, `CameraSystem.IsInCameraFrustum`), `nearestCut` (m), `crowd` (people found who are ambient crowd, the only ones a panic moves), `area`, `cooldown`.

### Reports

Every cast now posts four reports to the gate's `/report` (logged by `open77-mass-override-staging`, the last one kept in `/state`):

- `phase: cast` - what was asked: the probe counts plus `powerCut`, `powerSkipped`, `alarms`, `honks`, `terror`, `city` (state before), `cityForced`, `cityFuses`, `cityLights`, `hour` (in-game; CLS lights are off by day), `registry`, `registryNear`, `attachEvents`, `classes` (devices per class) and `build`.
- `phase: verify` - two seconds later, what took: `city` (now), `cut`, `stillCut`, `screensOn`, `lightsOn`, `alarms`, `alarmsOn`, `gone`.
- `phase: revert` - at 30 s: `cityReleased`, `restored`, `silenced`, `calmed`.
- `phase: settled` - two seconds after the revert: the same counters as verify; `stillCut` should be 0 and `city` should be `default`.

### 1.16.14: the levers V's own quickhacks use

The 1.16.13 casts reported 66 devices without power, 8 car alarms ringing and 47 lights that had been on, at 8 in the morning in Japantown, and nobody could tell: a vending machine with its screen off and a street lamp already off by day look like nothing happened. 1.16.14 replaced the power cut with what the game plays when V hacks something:

| What | Call | Source |
| --- | --- | --- |
| Vending machines, TVs, LCD screens, billboard devices, arcades, jukeboxes, radios, speakers | `QuestStartGlitch` through the device's controller (an `@addMethod` on `ScriptableDeviceComponentPS`, the action is protected) -> `StartGlitching`; a vending machine throws cans out | `scriptableDeviceBasePS.script`, `vendingMachine.script` |
| The same devices | `EMPHitEvent` (the EMP grenade's `emp_hit` sparks), ends on its own | `interactiveDevice.script` |
| Street lamps, spotlights, traffic, crossing and zebra lights, signs | `SetDeviceON` / `SetDeviceOFF` on a 0.5 s beat (blink) or a random 0.25 s flicker (blackout); the state at the cast is put back | `deviceBase.script` |
| Cars with crowd at the wheel | `EnableHighPriorityPanicDriving` + `ActivateNetrunnerQuickhack(Accelerate)` and the alarm; renewed every 6 s | `vehicleComponentPS.script` |

It also fixed a bug that had been there since the step log was added: `MassOverrideLog` opened `FileSystem.GetStorage("CapriConstruct")` a second time, and RedFileSystem answers that by revoking the storage for the whole session (`red4ext/logs/redfilesystem-*.log`: "Access to this storage has been permanently revoked"). The first line of the first cast locked Capri herself out of her settings, her history and the files Capri Voz answers in, which is also why no picture was ever saved. The log is now kept in memory and sent to the gate (`phase: log`); nothing in Mass Override opens a storage. Pictures are kept as `mass_override_<cast>_<phase>.txt` (base64).

Two casts on 2026-11-12, Japantown at 08:00 in-game: 21 machines glitching (21/21 at 2 s), 42 lights switching, 4 cars accelerating with panic driving, 9 alarms, 6 people panicking, all put back by the revert (`settled`: 0 glitching, 42/42 lights back as they were). V heard the horns; the street did not look different.

### 1.16.15: billboards, screens and every light on a hacked device

What makes Japantown bright is not devices. The billboards and ad screens are world advertisement nodes (`worldAdvertisementNode`) drawn by the ink advertisements layer, and the screens on walls and machines are world widgets; none has a device controller, so nothing in 1.16.14 could reach them. They are all ink, and Codeware hands out the ink system's layers and world widgets (`inkSystem.GetLayers`, `GetWorldWidgets`):

- `MassOverrideInk`: the root of every world ink layer (name contains advert, world or fluff; HUD, menus, notifications, loading and photo mode are never touched) and of every world widget is saved (opacity, tint) and put on the beat: lit in the beat's colour (red, cyan, magenta, acid green) or nearly gone; the blackout draws each one at random. The cast report names every layer (`inkNames`, the ones taken marked `*`) so the right one can be confirmed by name.
- `MassOverrideLights`: every `gameLightComponent` on a hacked device is switched and recoloured with `SetParameters` at three times its intensity, the call the game's own `ChangeLightEvent` ends in; its settings and on/off state are saved and put back.
- `MassOverrideFx`: V's screen plays `transition_glitch_loop` (the fast-forward glitch) for 1.5 s as the wave goes out and 0.6 s as the city comes back.
- The first cast of a session is blink now: a synchronised beat reads at once; a blackout by day changes little.

New report fields: `inkLayers`, `worldWidgets`, `inkTargets`, `lightComponents`, `inkNames` (cast) and `ink`, `lightComponents` (revert).

Verified on XyberRP Staging, 2026-11-12, Corpo Plaza at 03:00 in-game, blink: 59 machines glitching (59/59 at 2 s), 111 lights and 290 light components on the beat, the `inkAdvertisementsLayer` and `inkWorldLayer` roots plus 6 world widgets blinking in the hack colours, 5 cars accelerating with their alarms, 5 people panicking; `settled` had 0 glitching and 111/111 lights back as they were. V saw the street change.

### Production

XyberRP runs the same 1.16.15 scripts with its own gate:

| | Staging | Production |
| --- | --- | --- |
| Server | XyberRP Staging, `/opt/open77-xbuniverse-staging` | XyberRP, `/opt/open77-xbuniverse` |
| Gate | `open77-mass-override-staging`, 127.0.0.1:11900 | `open77-mass-override`, 127.0.0.1:11901 |
| Public base | `https://xyberrp.duckdns.org/mass-override-staging/` | `https://xyberrp.duckdns.org/mass-override/` |
| Package | `CapriPersonalityConstruct-1.16.15-massoverride-street.zip` | the same with the gate base swapped and the feed labelled `production` |

The scripts in this repo name the staging base; `mass-override/release/mo-build-prod-11615.py` makes the production package from the staging one and proves that only the gate base and the feed label changed. Both gates run the same `gate.js` and `dev-server.js` (`mass-override/deploy` has the units and the nginx locations), so each environment keeps its own cooldowns, casts and reports. The release scripts and how to run them are in `mass-override/release/README.md`.

### Compile check without the game

`scc.exe` pops a modal dialog when a compile fails, which is not acceptable while someone is playing. `scripts/MoScc.cs` (a 70-line wrapper, built with the .NET Framework `csc.exe`) loads the game's own `engine/tools/scc_lib.dll` and calls `scc_settings_disable_error_popup` before `scc_compile`. It compiles a sandbox copy of `r6/scripts` plus the three RED4ext plugin script folders against a copy of `r6/cache/final.redscripts`, so the running game's files are never touched. 1.16.11: `Completed with 603 warnings and 0 errors` (the same 603 as the game's own build); a deliberate call to a missing method failed with `UNRESOLVED_MEMBER` and no dialog.

### 1.16.17: every player runs every cast

On XyberRP a cast showed on the caster's screen and nowhere else. Three faults, all on the multiplayer side:

1. **The feed only started after a cast.** `MassOverrideFeed.Start` ran from `CapriMassOverride.RunWith`, so a game that had not cast never polled the gate at all.
2. **The feed only carried a mode.** `GET /feed` answered `"<seq> <mode>"`, and the game stored that mode for its own *next* cast (`ReceiveServerMode`). Nothing ran another player's cast.
3. **Every game was one player at the gate.** Casts registered as `EntityID.ToDebugString(V)`, which is the same on every PC, so one player's 40 s recharge refused everyone else's cast at the gate (and refused casts are not handed out).

What changed:

- **Every game polls from the start of its session.** `MassOverrideRegistry.OnAttach` (a `ScriptableSystem`, so once per session) starts a poller of its own generation; an older session's poller stops at its next tick. The poll re-arms itself every 2 s before anything else and never doubles a request still out (`StuckSeconds` 20).
- **Each game has its own id.** `MassOverridePrefs.Session()` (random, once per game run) goes with `/players` and `/cast`; the gate keys cooldowns by it and registers an unknown session on its first cast.
- **A cast carries what others need.** `/cast` sends where V stands (`x`, `y`, `z`), the mode the caster's game runs (the gate takes it instead of its own cursor, so nobody runs the other mode) and a token (`session-n`), which the caster's game remembers so the feed's copy is skipped there.
- **`GET /casts?since=N&session=S`** answers in plain text: `"<next>"`, then `"<seq> <mode> <x cm> <y cm> <z cm> <age ms> <ms left> <token>"` for every cast still on. The first answer of a session runs what is still on (a player who arrives during a blackout sees its rest). `/feed`, `/players` and `/cast` without a session keep answering older builds.
- **Another player's cast runs here** (`MassOverrideRemote`): the city's lights and the billboards for everyone in the session (`CityWide()`, they are the whole city's on the caster's screen too), and within `StreetReach()` (150 m) the street around the cast: the attach registry's devices within 120 m of the caster, the first probe from here when within 70 m, then the same per-target levers as the caster's (`MassOverrideApply.Targets`, shared with the caster's own cast) -- but no person is turned on this V, nothing is charged, and the crowd panics from the broadcast only.
- **One run on screen at a time.** `MassOverrideRevert.Arm` makes a run the active one; the next cast, here or anyone's, first calls `EndActive`, which puts the street back as it was (a run that saved the street mid-beat would put the beat's colours back for good). A revert that ran early does nothing when its scheduled call comes.
- Every remote run reports `phase: remote` (and `remote-revert`) to the gate with its distance, street/city, counts and the session; the gate logs `[cast]` with the position and how many games are polling, and `[feed] new client ...` for every session that starts polling. `GET /state` lists the pollers and the recent casts.

Checked: the game's own compiler (REDscript 1.0.0-preview.22, the owner's laptop): 107 files, 521 warnings, 0 errors, nothing to migrate; `node --test` for the gate (15 dev-server tests, 5 new: sessions, positions, `/casts`, older builds, bad input, pollers); `reds-lint` clean.

## 1.16.18: a cast reaches the gate from a PC whose connection drops

On 2026-11-12 a cast from the laptop ran on the laptop only: its one `POST /cast` was lost to the PC's
connection ("Recv failure: Connection was reset"; minutes before, "Failed to connect ... after 21025 ms"),
so the gate never had it and no other game ran it. Since 1.16.18:

- `MassOverrideCastSend` posts the cast straight to `/cast` (the gate registers a session it does not
  know; a 404 from an older gate registers first) and sends it again while no answer has come: tries at
  0, 3, 7, 12, 17 and 22 s, given up after 26 s with a log line saying the cast ran on that screen only.
  A try still out is not waited for.
- The gate answers a cast whose token it already has with that cast (`duplicate: true`): never handed out
  twice, never charged twice, no recharge refusal for the caster's own retry (`[cast] again from ...` in
  its log, `stats.again` in `/state`). A body it cannot read is said in its log (`[http] ... -> 400`).
- Every report (`/report`, phase `log`) carries the game's `session`: `playerId` is V's entity id,
  `dynamic: '1'` on every PC.

The brain (`client/mcp/capri-brain.mjs`, build `2026-11-12.1`) also answers Mass Override however V types
it -- "mass over ride" went to the model, which answered with banter and no cast -- and its journal says
for each request whether the model chose Mass Override itself (`mo=model`) or not (`mo=no`).

## Verification status

- Node tests: `gate.test.js` 13, `engine-adapter.test.js` 7, `dev-server.test.js` 10, `reds-lint.test.js` 8, `reds-lint-angle.test.js` 2 - 40/40 pass (run each file with `node --test`).
- Game scripts: `scripts/MoScc.cs` against a copy of the game's scripts, `Completed with 603 warnings and 0 errors` for 1.16.15 and for its production variant (the same 603 warnings as the game's own build).
- In game: 1.16.15 on XyberRP Staging, cast by a player and seen working (see 1.16.15 above), with every report from cast to final.
- Production: XyberRP serves 1.16.15 with the production gate; checked with `mo-verify-prod-11615.py` (manifest, blob hash, scripts inside, gate base), and `mo-gate-check.sh` showed each public route reaching its own gate. No production cast has been made yet.

## Open items

1. Cooldown value (120 s placeholder).
2. Cost resource and amount (25 RAM placeholder).
3. Probe budget and reach: 64 × 25 m is a starting point, not a measurement.
4. Whether component toggling is enough for every light type, or some need `ToggleLight`.
5. Whether the revert should restore a device that was already off.
6. Whether a 1 s blink pulse over 1000 targets is cheap enough, or the interval needs to be longer.
7. Whether the cache should also keep people per cell, refreshed rather than reused, so a repeat flood reaches the same distance.
