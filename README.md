<p align="center">
  <img src="https://github.com/nobody71004/open77-capri/releases/download/capri-header-v1/capri-header.png" alt="Capri" width="100%">
  <br>
  <sub>Mirror: <a href="https://files.catbox.moe/y070lo.png">files.catbox.moe</a></sub>
</p>

# Open77 Capri

Capri: Personality Construct integration for **Open77 multiplayer** servers.

## Contents

- [What is included](#what-is-included)
- [What is not included](#what-is-not-included)
- [Requirements](#requirements)
- [Server quick start](#server-quick-start)
- [Launcher-delivered client mod](#launcher-delivered-client-mod)
- [Client setup](#client-setup)
- [Important behaviour](#important-behaviour)
- [Verification](#verification)
- [Troubleshooting and rollback](#troubleshooting-and-rollback)
- [License](#license)

This repository contains the server-side work we added for Capri plus the exact
reference scripts used to package Capri alongside Codeware. It is written so
another Open77 operator can reproduce the setup without copying our server,
database, credentials, or third-party mod binaries.

## What is included

- **Ripperdoc OS chip** — a server-side `ripperdoc.lua` catalogue entry for
  `capri_personality_construct` in the Operating System slot.
- **`RP_SOLD` opt-in** — the small `module.lua` change that lets a forbidden
  `rp` item be listed and sold by the clinic.
- **EN/FR locale keys** — name, grade and description for the chip.
- **Capri + Codeware package split** — reference scripts that move the five
  Codeware Redscript dependencies into the Capri package and remove them from
  the Codeware package, avoiding duplicate Redscript definitions on the client.
- **Codeware repair reference** — the exact dependency/package repair used when
  the Codeware asset package was missing from an Open77 install.
- **Launcher-delivered mod** — a packager and server publisher that make Capri
  an Open77 `requiredMods` package the launcher installs on connect. See
  [docs/LAUNCHER_MOD.md](docs/LAUNCHER_MOD.md).
- **Install, verification, rollback and troubleshooting docs.**
- **Optional client tooling** — CapriVoz/OmniVoice example, admin-only CET
  control bridge, and a local OpenAI-compatible Capri brain server. None of it is
  required for a server to sell the chip, and the launcher package does not ship
  any CET UI.

## What is not included

Third-party files are **not redistributed** here:

- the Capri: Personality Construct archive, DLL, CET scripts or Redscript source;
- Open77/OPX Infinity source or server data;
- Codeware, ArchiveXL, Red4ext, Cyberpunk 2077 or any other mod binaries;
- any generated voice clips;
- `.env` files, API keys, SSH keys, server addresses, database credentials or
  player data.

Install those from their official sources and follow their licenses. See
[NOTICE.md](NOTICE.md).

## Requirements

Server:

- Linux Open77 server, root access, `systemd`.
- Python **3.10+** (the patcher uses modern type syntax).
- An existing server root with
  `resources/opx_infinity/config/ripperdoc.lua`,
  `resources/opx_infinity/modules/ripperdoc/module.lua` and
  `resources/opx_infinity/modules/ripperdoc/locales.lua`.
- A backed-up server and a maintenance window.

Client (for players who use the companion):

- Cyberpunk 2077 with Codeware, ArchiveXL and Red4ext installed by the launcher
  or from their official sources.
- Open77 Launcher, if you want Capri delivered automatically on connect.

## Server quick start

```bash
cp .env.example .env
sudo OPEN77_ROOT=/opt/open77-xbuniverse \
     OPEN77_SERVICE=open77-xbuniverse.service \
     bash scripts/install_capri_clinic.sh
sudo OPEN77_ROOT=/opt/open77-xbuniverse \
     OPEN77_SERVICE=open77-xbuniverse.service \
     bash scripts/verify_capri_clinic.sh
```

The installer:

1. backs up each touched file as `*.before-capri-chip` (once);
2. adds the catalogue entry;
3. adds the `RP_SOLD` opt-in;
4. adds the EN/FR locale keys;
5. restarts only the service you name and checks it stays active.

It does **not** modify `server.jsonc` and does **not** enable `unsecured`.
Do not expose an unsecured Open77 server to the public internet.

For staging, use the staging root and staging service. Test staging first, then
repeat against production. Full instructions:
[docs/SERVER_INSTALL.md](docs/SERVER_INSTALL.md).

## Launcher-delivered client mod

The packager turns a Capri build into a launcher package and the publisher
registers it as a server `requiredMods` entry. Players then receive it when they
connect. Build, publish, and check the manifest as described in
[docs/LAUNCHER_MOD.md](docs/LAUNCHER_MOD.md). In short:

```bash
python scripts/build_capri_launcher_mod.py --capri-zip <capri.zip> \
       --version <x.y.z> --out-dir <dist-dir>
```

Build outputs, zips and checksums are generated locally and must not be
committed.

## Client setup

Follow [docs/CLIENT_SETUP.md](docs/CLIENT_SETUP.md) for the manual install path.
It covers the package layout, the in-game keys (F7 / CapsLock / Enter by
default), and the optional CET and voice tooling. The launcher package does not
ship any CET UI.

## Capri package split

If your client gets duplicate Codeware/Redscript symbols, or if Capri is not
being packaged with its Codeware dependencies, read
[docs/PACKAGE_SPLIT.md](docs/PACKAGE_SPLIT.md).

The scripts in `scripts/reference/` are the **exact pinned implementation** used
on our server for:

- Capri `1.16.0` → `1.16.1`
- Codeware `1.21.0-open77r2` → `1.21.0-open77r3`

They contain destructive blob cleanup and are intentionally not run by the
clinic installer. Review the constants and backups before running them; adapt
them if your versions or Open77 package layout differ.

## Important behaviour

The chip is an **inventory item**. Buying or equipping it does not summon the
Capri hologram. The companion is a separate client mod. The Open77 Launcher can
deliver it as a server-required mod and install it when the player connects; see
[docs/LAUNCHER_MOD.md](docs/LAUNCHER_MOD.md) and
[docs/CLIENT_SETUP.md](docs/CLIENT_SETUP.md).

## Verification

- [docs/VERIFY.md](docs/VERIFY.md) — server, client package, clinic and in-game
  checks.
- [docs/ROLLBACK.md](docs/ROLLBACK.md) — restore the clinic and package split.
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — chip not listed, Capri
  invisible, duplicate Codeware symbols, voice/brain issues.

## License

Original scripts and documentation in this repository are MIT-licensed. See
[LICENSE](LICENSE). Third-party components are not covered by that license and
are not included.
