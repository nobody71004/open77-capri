# Client setup

The Capri companion is a separate client mod. The server chip only adds the
OS-slot inventory item; it does not install or summon the companion.

If your Open77 server requires Capri, the launcher installs it when you connect:
accept the named package, let it download and verify, then launch. Do not copy
Capri files by hand in that case; a manual copy is a foreign mod and the launcher
will not overwrite it. See [LAUNCHER_MOD.md](LAUNCHER_MOD.md).

## 1. Install Capri from its official source (manual or solo)

Install **Capri: Personality Construct** `1.16.x` from its official mod page.
This repository does not redistribute its archive, DLL, CET scripts, Redscript
or voice assets.

The client package needs its normal dependencies, typically:

- RED4ext, Redscript, Codeware, ArchiveXL, TweakXL;
- Mod Settings, RedData, RedFileSystem, RedHttpClient;
- Cyber Engine Tweaks for the Capri window.

The package should contain:

```
archive/pc/mod/CapriPersonalityConstruct.archive
red4ext/plugins/CapriPersonalityConstruct/
bin/x64/plugins/cyber_engine_tweaks/mods/CapriVozReady/
r6/scripts/CapriPersonalityConstruct/
```

The launcher package deliberately contains **no CET UI**. It does not include
`bin/x64/plugins/cyber_engine_tweaks/mods/CapriPersonalityConstruct/` (the F1
chat/settings window). Only the no-UI `CapriVozReady` heartbeat is kept.
Administrators who need the CET window install it separately on their own
machine; it is never delivered to players.

If your Open77 server distributes Capri as a package, use the package-split
procedure in [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md) so the five Codeware
dependencies are not present twice.

## 2. CapriVoz / OmniVoice (optional but recommended)

CapriVoz provides her voice and ears. The launcher package carries the CapriVoz
scripts and voice profiles next to the plugin; the RED4ext plugin starts it with
the game. On first launch it uses a Windows voice, so she is audible with no
extra setup. Her cloned voice and ears need the optional local engine (about
900 MB) installed from Capri's Connection tab or http://localhost:4325; it is a
per-machine install and is not redistributed. To use an external
OpenAI-compatible TTS server instead, set its endpoint, normally:

```text
http://127.0.0.1:8880/v1
voice: capri
```

`client/Iniciar OmniVoice.bat.example` shows the CPU/CUDA selection used on our
machine: CUDA when Cyberpunk is closed, CPU while it is running so the game
keeps its VRAM. The local OmniVoice model files are not included.

## 3. In-game controls

After loading a save, outside the ripperdoc menu:

- **F7** — summon Capri (default; may be suppressed in menus).
- **CapsLock** — hold to talk through the microphone.
- **Enter** — open the text input.

These are Capri Redscript input actions, not Open77 `RegisterKeyMapping`
actions. They are configured in Capri's Mod Settings page and do not appear in
Open77's keybind tab. The player package does not include the Capri CET window,
so there is no F1 chat/settings window on a player install.

## 4. Choose her brain (admin machine)

The player package has no CET Connection tab. Configure the provider on the
admin machine through the `CapriMcpBridge` command file (or the separately
installed official CET window), then distribute the resulting
`r6/storages/CapriConstruct/settings.json` as part of the server's client
profile. The provider choices are the same:

- **Player2** — connect through the Player2 app or the browser device flow;
- **Gemini (free)** — needs a Google AI Studio key;
- **OpenRouter/OpenAI** — needs the provider's key;
- **On your PC (Ollama, LM Studio)** — no account; the server must be running;
- **Other OpenAI-compatible** — URL, optional key and model.

The chip does not choose a provider. A connected provider is what makes her
generate lines.

## Optional local brain + CET bridge

`client/mcp/capri-brain.mjs` is a small OpenAI-compatible endpoint. Capri's
**local** provider points at it through CapriVoz. Configure it from the admin
machine; the player package has no CET settings window:

```bash
node client/mcp/capri-brain.mjs
# health: http://127.0.0.1:8890/health
```

Default backend is Ollama `llama3.2:3b`; `CAPRI_BRAIN_BACKEND=freebuff` uses
the Freebuff API if `OPENAI_API_KEY` is set. The optional CET bridge
`client/cet/CapriMcpBridge/init.lua` lets an MCP host read/configure Capri's
provider and call test/summon functions. See [client/README.md](../client/README.md)
and [client/mcp/README.md](../client/mcp/README.md).

Never commit `settings.json`, `.env`, CapriVoz keys or provider keys.
