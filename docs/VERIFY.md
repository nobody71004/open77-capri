# Verification

## Server files

```bash
sudo OPEN77_ROOT=/opt/open77-xbuniverse \
     OPEN77_SERVICE=open77-xbuniverse.service \
     bash scripts/verify_capri_clinic.sh
```

Manual checks:

```bash
ROOT=/opt/open77-xbuniverse
grep -n "capri_personality_construct" \
  "$ROOT/resources/opx_infinity/config/ripperdoc.lua"
grep -n "entry.RP_SOLD == true" \
  "$ROOT/resources/opx_infinity/modules/ripperdoc/module.lua"
grep -n "ripperdoc.item.capri" \
  "$ROOT/resources/opx_infinity/modules/ripperdoc/locales.lua"
systemctl is-active open77-xbuniverse.service
```

Expected:

- entry has `SYSTEM = 'operating_system'`, `SLOT = 'operating_system'`,
  `KIND = 'rp'`, `RP_SOLD = true`, `TIER = 4`, `CAPACITY = 16`,
  `REMOVE = 250`, `WEAR = 2`;
- prototype grade price `2500`, icon `cw_cyberdeck_arasaka`;
- six locale keys total (three EN, three FR);
- service active; Open77's root HTTP endpoint commonly returns `404`, which is
  normal for this service.

## Package split

On staging:

```bash
ROOT=/opt/open77-xbuniverse-staging
python3 - <<'PY'
import json
p = '/opt/open77-xbuniverse-staging/server.jsonc'
data = json.load(open(p))
for package in data.get('requiredMods', {}).get('packages', []):
    if package.get('id') in ('capri-personality-construct', 'codeware-assets'):
        print(package)
PY
```

Check the versions, SHA-256 and size against the new blobs. Confirm the new
Capri zip contains **44 files**, including only the no-UI `CapriVozReady` CET
backend and the five `r6/scripts/Codeware/*.reds` files under
`r6/scripts/CapriPersonalityConstruct/Codeware/`. It must contain no
`CapriPersonalityConstruct/init.lua` and no other CET UI. Confirm the new
Codeware zip has no `r6/scripts/Codeware/` entries.

Client log:

```text
r6/logs/redscript_rCURRENT.log
```

A healthy staging load showed **0 errors**, the Capri archive present, the
Capri RED4ext DLL loaded, and CapriVoz's `voz_latido.json` heartbeat updating.

## Launcher delivery

On the server (game port + 1):

```bash
curl -sS http://127.0.0.1:<game port + 1>/mods/v1/manifest | python3 -m json.tool
```

The manifest must list `capri-personality-construct` with `source: hosted`, the
pinned `sha256`/`sizeBytes`, `enabled: true`, and a digest that matches its
packages. `requiredMods.unsecured: true` is a `server.jsonc` policy, not a
manifest field; confirm it there. Fetch the blob and hash it:

```bash
SHA=<sha256>
curl -sS "http://127.0.0.1:<game port + 1>/mods/v1/blobs/$SHA" | sha256sum
```

On the client, the launcher must show **Preparing server mods**, name Capri and
install it before the game starts. If it refuses with `ProjectionRefused`, a
manual Capri copy owns one of the paths; remove the manual copy first.

## In-game clinic

Use a test character:

1. Chip is visible in the ripperdoc **Operating System** section.
2. Buy/equip writes the expected chrome and ledger rows.
3. OS slot shows the chip; no combat stats.
4. Remove/re-equip works; no duplicate chip.
5. Production is tested only after staging passes.

## Companion (no player CET UI)

The chip is not the companion trigger. The delivered package carries no Capri
CET window, so there is no F1 chat/settings window to test on a player install.
To verify the companion itself:

1. Load a save outside the clinic menu.
2. Press **F7** — Capri's summon key from her Redscript Mod Settings — and
   confirm her figure or face appears.
3. Hold **CapsLock** and confirm the talk path; press **Enter** for the text box.
4. Check the `CapriVozReady` line in the CET log (`[CapriVozReady] auto: ...`) to
   confirm the no-UI voice heartbeat ran after the save loaded.
5. For provider/model changes, use the admin MCP bridge or edit
   `r6/storages/CapriConstruct/settings.json`; the player-facing CET Connection
   tab is not part of the launcher package.

These keys are Capri Redscript actions, not Open77 `RegisterKeyMapping` actions,
so they do not appear in Open77's keybind tab.

## Optional brain

```bash
curl -sS http://127.0.0.1:8890/health
curl -sS http://127.0.0.1:8890/v1/models
```

Then a short chat request. A working local endpoint returns an OpenAI-style
`choices[0].message.content`. The game-facing provider URL is the one Capri's
`localUrl` points to, and CapriVoz must be running for the relay.
