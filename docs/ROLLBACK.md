# Rollback

## Clinic chip

The installer creates these once, next to the originals:

```
resources/opx_infinity/config/ripperdoc.lua.before-capri-chip
resources/opx_infinity/modules/ripperdoc/module.lua.before-capri-chip
resources/opx_infinity/modules/ripperdoc/locales.lua.before-capri-chip
```

Restore them and restart the unit:

```bash
ROOT=/opt/open77-xbuniverse
for f in \
  resources/opx_infinity/config/ripperdoc.lua \
  resources/opx_infinity/modules/ripperdoc/module.lua \
  resources/opx_infinity/modules/ripperdoc/locales.lua; do
  if [ -f "$ROOT/$f.before-capri-chip" ]; then
    cp -a "$ROOT/$f.before-capri-chip" "$ROOT/$f"
  fi
done
systemctl restart open77-xbuniverse.service
systemctl is-active open77-xbuniverse.service
```

The chip may remain on characters that already bought it. That is player data;
do not delete it unless you have a separate, backed-up data migration plan.

## Package split

The split scripts back up the old blobs, sidecars, `server.jsonc` and
`resources/codeware/open77.lua` under:

```
/tmp/codeware-r2/backup-capri-split-<environment>-<timestamp>/
```

Restore those files, restore the old `.open77/mods/<sha>.blob` and `.json`
files, remove the new blobs only after confirming they are not referenced, and
restart the unit. Do not delete `.open77/mods` wholesale.

## Optional brain

- Restore `settings.json.before-capri-brain` if you changed the provider.
- Stop the local brain with `capri_brain_stop` or terminate the PID recorded in
  `%LOCALAPPDATA%\CapriVoz\mcp-brain.pid`.
- Remove `CapriMcpBridge` from CET only if you no longer want the control bridge.

## Never roll back by

- deleting the whole server root or `.open77/mods` directory;
- setting `unsecured=true` to work around a startup problem;
- overwriting `server.jsonc` without a JSON validation and a backup.
