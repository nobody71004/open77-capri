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
Capri zip contains 44 files and the five `r6/scripts/Codeware/*.reds` files
under `r6/scripts/CapriPersonalityConstruct/Codeware/`; confirm the new Codeware
zip has no `r6/scripts/Codeware/` entries.

Client log:

```text
r6/logs/redscript_rCURRENT.log
```

A healthy staging load showed **0 errors**, the Capri archive present, the
Capri RED4ext DLL loaded, and CapriVoz's `voz_latido.json` heartbeat updating.

## In-game clinic

Use a test character:

1. Chip is visible in the ripperdoc **Operating System** section.
2. Buy/equip writes the expected chrome and ledger rows.
3. OS slot shows the chip; no combat stats.
4. Remove/re-equip works; no duplicate chip.
5. Production is tested only after staging passes.

## Companion

The chip is not the companion trigger. To verify Capri herself:

1. Load a save outside the clinic menu.
2. **F1 → Appearance → Show on HUD** — should show her face and test line.
3. **F1 → Appearance → Take her outside** — should show her body.
4. **F1 → Connection** — provider status, key/model and Player2 state.
5. **F1 → Voice → Test voice** — CapriVoz/OmniVoice path.

If the F1 window does not open at all, CET is not drawing; that is separate from
the clinic patch.

## Optional brain

```bash
curl -sS http://127.0.0.1:8890/health
curl -sS http://127.0.0.1:8890/v1/models
```

Then a short chat request. A working local endpoint returns an OpenAI-style
`choices[0].message.content`. The game-facing provider URL is the one Capri's
`localUrl` points to, and CapriVoz must be running for the relay.
