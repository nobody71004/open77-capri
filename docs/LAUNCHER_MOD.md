# Launcher-delivered Capri

Capri can be a **server-required mod**: the Open77 Launcher downloads it when the
player connects and installs it into the game folder before Cyberpunk starts.
Players do not copy Capri files by hand, and the chip, the companion and her
voice arrive together.

This is the Open77 `requiredMods` path, not a resource package. The launcher
owns the files it installs and removes them when the player joins a world that
does not require them.

## How it works

```text
server.jsonc                      Open77 Launcher                 Game folder
────────────                      ───────────────                 ───────────
requiredMods.packages  ────────►  GET /mods/v1/manifest           archive/pc/mod/…
  capri-personality-construct     GET /mods/v1/blobs/<sha256>     red4ext/plugins/…
  source: hosted                  verify SHA-256                  r6/scripts/…
  version / sha256 / sizeBytes    project at Connect             bin/x64/plugins/cet/mods/…
                                  switch to the world profile
```

The launcher resolves every requirement before it starts the game, asks the
player once when the package carries executable content, downloads the blob,
verifies the pinned hash, and only then writes the files. Connecting to another
world removes the previous world's layer and restores the player's profile.

## Requirements

- Open77 server with `requiredMods` support (2.50 line; the server must serve
  `/mods/v1/manifest` on **game port + 1**).
- `requiredMods.enabled: true` and `requiredMods.unsecured: true` on the server.
  Capri contains a DLL, Redscript, CET Lua, a PowerShell script and a batch file.
  Open77 deliberately refuses unreviewed executable content from a secure
  world; `unsecured` is what makes the launcher warn the player by name and let
  them accept. **Do not expose an unsecured world to the public internet
  without understanding that policy.** The publisher refuses to flip this flag
  itself.
- The launcher's normal prerequisites: RED4ext, Redscript, CET, ArchiveXL,
  TweakXL, Codeware and the Mod Settings stack. The server's base profile
  supplies them; Capri does not bundle them.

## Build the package

The official Capri release is the input. This repository does not redistribute
it. Include the five Codeware scripts from the game install so the package
matches the Open77 split (see [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md)):

```bash
python scripts/build_capri_launcher_mod.py \
  --capri-zip "$HOME/Downloads/CapriPersonalityConstruct-1.16.zip" \
  --codeware-scripts "/path/to/Cyberpunk 2077/r6/scripts/CapriPersonalityConstruct/Codeware" \
  --version 1.16.2 \
  --out-dir dist
```

On Windows:

```powershell
python scripts\build_capri_launcher_mod.py `
  --capri-zip "$env:USERPROFILE\Downloads\CapriPersonalityConstruct 1.16.zip" `
  --codeware-scripts "C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077\r6\scripts\CapriPersonalityConstruct\Codeware" `
  --version 1.16.2 --out-dir dist
```

The builder:

- rejects traversal, absolute paths and anything outside an Open77 mod root;
- drops player storage, generated voice cache, logs and per-user CapriVoz
  `config.json` (local paths and keys must never travel);
- adds the five Codeware `.reds` files when supplied;
- writes a reproducible zip (fixed timestamps) plus `<sha256>.json`;
- prints the exact `requiredMods` entry for the server.

Expected result for Capri 1.16.2: **44 files**, the three required roots plus
`r6/scripts`, only the no-UI `CapriVozReady` CET backend, and a SHA-256 that is
stable across machines. The builder removes every player-facing CET mod,
including `CapriPersonalityConstruct/init.lua` (the F1 chat/settings window).
The package must contain no CET UI at all.

## Publish on the server

Copy the zip to the server, then run as root:

```bash
sudo bash scripts/publish_capri_launcher_mod.sh staging \
     --zip dist/CapriPersonalityConstruct-1.16.2.zip --version 1.16.2
```

The publisher:

1. validates the archive the same way the launcher will;
2. stores it as `.open77/mods/<sha256>.blob` with a `<sha256>.json` sidecar;
3. backs up `server.jsonc` once as `server.jsonc.before-capri-launcher-mod`;
4. adds or updates the `capri-personality-construct` entry under
   `requiredMods.packages`, with `source: "hosted"` and the pinned hash/size;
5. refuses to restart while players are connected unless `--force` is given;
6. restarts the unit, then verifies `/mods/v1/manifest` (entry, digest, enabled)
   and `/mods/v1/blobs/<sha256>` (bytes hash to the same value). The
   `unsecured` policy lives in `server.jsonc` under `requiredMods`; the manifest
   exposes `enabled`, the digest and the package list.

Test staging first, with a launcher client:

1. Connect to staging. The launcher shows **Preparing server mods**, names
   Capri and asks before installing executable content.
2. Accept. The launcher downloads the blob, verifies the hash and installs it.
3. Cyberpunk starts. Capri's DLL, archive and Redscript are present; the clinic
   chip can be equipped and Capri can be summoned. There is no Capri CET window
   to open; the package carries no CET UI.
4. Connect to a world that does not require Capri. The launcher removes the
   world layer; the manual install is not touched.

Only then publish production:

```bash
sudo bash scripts/publish_capri_launcher_mod.sh production \
     --zip dist/CapriPersonalityConstruct-1.16.2.zip --version 1.16.2
```

## Her voice

The archive includes `red4ext/plugins/CapriPersonalityConstruct/CapriVoz/`,
including `CapriVoz.ps1` and the voice profiles. The RED4ext plugin starts
CapriVoz for the running game; the player does not launch it separately.

The archive also carries the `CapriVozReady` CET resource. After a save loads,
it calls Capri's public `SetVoiceSource`/`CheckCapriVoz` health check, clearing
the automatic "Capri Voz closed" cooldown when the heartbeat is moving. CET is
sandboxed and cannot launch processes; the RED4ext plugin remains the starter.

The TTS engine and its model (OmniVoice, Kokoro, Pocket, etc.) are **not**
redistributed here. That does not leave her mute: on first launch CapriVoz
creates `config.json` next to the script and uses a Windows voice, so audio
works before any setup. Her cloned voice and her ears need the optional local
engine (Pocket TTS + faster-whisper, about 900 MB) installed once from the local
CapriVoz page at http://localhost:4325. The player package does not ship the
Capri CET window that used to host that installer. It downloads into
`%LOCALAPPDATA%\CapriVoz\motor`, not the game folder. Provider keys and a custom
OpenAI-compatible endpoint are per-machine settings; do not put them in the
package.

## No player CET UI

The launcher package is player-facing, so it carries **no CET UI**. The builder
removes every file under `bin/x64/plugins/cyber_engine_tweaks/mods/` except
`CapriVozReady/init.lua`, and the publisher refuses a zip that contains any
other CET entry. That removes:

- `CapriPersonalityConstruct/init.lua`, the F1 chat/settings window and its
  hotkeys;
- `CapriMcpBridge`, the admin-only backend control plane, if it is ever present
  in the source release.

`CapriVozReady` is kept because it has no draw handler: after a save loads it
calls Capri's public `SetVoiceSource`/`CheckCapriVoz` health check so the voice
server's heartbeat clears the automatic cooldown. The backend bridge and any
admin diagnostics are installed separately on an administrator's machine; they
are never delivered by the launcher.

Because the player package has no CET window, there is no Capri CET keybind to
list in Open77's keybind tab. Open77's tab only shows mappings registered with
`RegisterKeyMapping`; Capri's summon and talk keys are Redscript actions set in
Capri's own Mod Settings page. With the CET window removed, configure providers,
models and voice on the admin machine, or let the player use the preconfigured
`r6/storages/CapriConstruct/settings.json`.

## Security and review

- The package is executable content. On an `unsecured` world the launcher
  lists it individually and asks the player; on a secure world it refuses it.
- The server's Warden has a **Required mods** tab with `request-review` for the
  exact blob hash. Once OPEN//77 verifies those bytes, the package can be served
  from a secure world too. That review is outside this repository.
- Never put provider keys, SSH keys, `.env` files or player data in the zip.
  The builder refuses the known runtime files, but review the output anyway.

## Rollback

```bash
ROOT=/opt/open77-xbuniverse          # or -staging
cp -a "$ROOT/server.jsonc.before-capri-launcher-mod" "$ROOT/server.jsonc"
systemctl restart open77-xbuniverse.service   # or the staging unit
```

The blob stays content-addressed in `.open77/mods`; it is harmless when no
`requiredMods` entry references it. Do not delete the whole blob directory.
Players who already installed Capri keep it until they connect to a world that
does not require it (the launcher then removes the world layer).

## Troubleshooting

- **Manifest 404 / connection refused** — `resources.download` is disabled or
  the server is not listening on game port + 1. The launcher's direct-manifest
  contract requires that port.
- **`required_mods_refused` / `UnverifiedExecutable`** — `unsecured` is false,
  or the blob hash does not match the config. Re-run the publisher and read its
  verification output.
- **`ProjectionRefused` naming a Capri path** — a manual Capri install owns that
  file. Remove the manual copy (or let the launcher quarantine it) before
  connecting; the launcher will not overwrite another manager's file.
- **`mod_attestation_unavailable`** — the Open77 master is unreachable. The
  launcher fails closed; retry when it is back.
- **No audio** — CapriVoz is running but the local TTS engine/model is missing.
  Install it once through CapriVoz or `CapriLauncher.exe`.
