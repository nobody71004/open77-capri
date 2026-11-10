# Architecture

There are four separate layers. Keeping them separate avoids the common
assumption that buying the clinic chip makes the companion appear.

```
Open77 server                         Player's game
─────────────                         ─────────────
ripperdoc.lua catalogue  ── clinic ──► OS tab item
module.lua RP_SOLD                      │
locales.lua EN/FR                       │ equip (inventory only)
                                        │
Open77 Launcher      ─ requiredMods ──► Capri client package
  /mods/v1/manifest                     ├─ archive/pc/mod/*.archive
  hash-verified blob                    ├─ red4ext/plugins/Capri...
  projected at Connect                  ├─ CET Capri window
                                        └─ r6/scripts/Capri...
                                             │
                                      CapriVoz / OmniVoice
                                             │
                                      optional LLM provider
```

## Server clinical layer

`resources/opx_infinity/config/ripperdoc.lua` adds the `capri_personality_construct`
catalogue entry. `modules/ripperdoc/module.lua` gets the `RP_SOLD` opt-in so the
forbidden `rp` item is intentionally sold. `locales.lua` gets EN/FR strings.
No database migration is involved: Open77 reads the catalogue from Lua and the
normal chrome/ledger tables record purchases.

## Launcher delivery layer

A world can declare Capri in `requiredMods`. The launcher reads
`/mods/v1/manifest` before it starts the game, downloads the pinned blob,
verifies its SHA-256, and projects the files into the game folder. It owns those
files as a world profile and removes them when the player joins a world that
does not require them. This is the supported way to make the companion arrive
with the server; see [LAUNCHER_MOD.md](LAUNCHER_MOD.md).

## Client package layer

Capri's client package and Codeware both shipped `r6/scripts/Codeware/*.reds` in
the versions used here. The split moves those five scripts into the Capri
package and makes the Codeware package dependency-only. That is a packaging
change, not a gameplay change. See [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md).

## Companion layer

The Capri mod is a client-side companion. Its summon key (F7), HUD and voice are
independent of the server item. The player package does not ship Capri's CET
window (F1); that window and the backend MCP bridge are admin-only installs. The
chip is an OS-slot inventory item; it does not call `CapriSystem.Summon()`.

## Optional brain layer

Capri can think through Player2, Gemini, OpenRouter, OpenAI, a local Ollama/LM
Studio server, or any OpenAI-compatible endpoint. The optional
`client/mcp/capri-brain.mjs` exposes a local OpenAI-compatible endpoint; CapriVoz
relays `http://` provider calls from the game because RedHttpClient only sends
to HTTPS. The CET bridge can change provider settings and invoke public
CapriSystem methods without simulating clicks.
