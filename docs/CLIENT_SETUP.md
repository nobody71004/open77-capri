# Client setup

The Capri companion is a separate client mod. The server chip only adds the
OS-slot inventory item; it does not install or summon the companion.

## 1. Install Capri from its official source

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
bin/x64/plugins/cyber_engine_tweaks/mods/CapriPersonalityConstruct/
r6/scripts/CapriPersonalityConstruct/
```

If your Open77 server distributes Capri as a package, use the package-split
procedure in [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md) so the five Codeware
dependencies are not present twice.

## 2. CapriVoz / OmniVoice (optional but recommended)

CapriVoz provides her voice and ears. Put the CapriVoz folder next to the Capri
plugin and set its local OmniVoice endpoint, normally:

```text
http://127.0.0.1:8880/v1
voice: capri
```

`client/Iniciar OmniVoice.bat.example` shows the CPU/CUDA selection used on our
machine: CUDA when Cyberpunk is closed, CPU while it is running so the game
keeps its VRAM. The local OmniVoice model files are not included.

## 3. In-game controls

After loading a save, outside the ripperdoc menu:

- **F1** — Capri/CET window; use **Appearance → Show on HUD** to force a visual
  test without an LLM.
- **F7** — summon Capri (default; may be suppressed in menus).
- **CapsLock** — hold to talk through the microphone.
- **Enter** — open the text input.

If F7 does nothing, use the F1 Appearance buttons. The Mod Settings page does
not always expose these key overrides, but the buttons call the same functions.

## 4. Choose her brain

In **F1 → Connection** you can choose:

- **Player2** — connect through the Player2 app or the browser device flow;
- **Gemini (free)** — needs a Google AI Studio key;
- **OpenRouter/OpenAI** — needs the provider's key;
- **On your PC (Ollama, LM Studio)** — no account; the server must be running;
- **Other OpenAI-compatible** — URL, optional key and model.

The chip does not choose a provider. A connected provider is what makes her
generate lines.

## Optional local brain + CET bridge

`client/mcp/capri-brain.mjs` is a small OpenAI-compatible endpoint. Capri's
**local** provider points at it through CapriVoz:

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
