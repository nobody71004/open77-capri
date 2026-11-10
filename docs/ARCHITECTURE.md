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
Open77 package layer  ─── download ───► Capri client package
  Capri 1.16.x + five                   ├─ archive/pc/mod/*.archive
  Codeware scripts                      ├─ red4ext/plugins/Capri...
  Codeware dependency-only              ├─ CET Capri window
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

## Client package layer

Capri's client package and Codeware both shipped `r6/scripts/Codeware/*.reds` in
the versions used here. The split moves those five scripts into the Capri
package and makes the Codeware package dependency-only. That is a packaging
change, not a gameplay change. See [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md).

## Companion layer

The Capri mod is a client-side companion. Its own CET window (F1), summon key
(F7), HUD and voice are independent of the server item. The chip is an OS-slot
inventory item; it does not call `CapriSystem.Summon()`.

## Optional brain layer

Capri can think through Player2, Gemini, OpenRouter, OpenAI, a local Ollama/LM
Studio server, or any OpenAI-compatible endpoint. The optional
`client/mcp/capri-brain.mjs` exposes a local OpenAI-compatible endpoint; CapriVoz
relays `http://` provider calls from the game because RedHttpClient only sends
to HTTPS. The CET bridge can change provider settings and invoke public
CapriSystem methods without simulating clicks.
