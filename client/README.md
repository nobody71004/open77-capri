# Optional client tooling

Nothing in this folder is required to sell the clinic chip. These are the
client-side pieces used while developing and testing Capri.

## Contents

| Path | Purpose |
|---|---|
| `cet/CapriMcpBridge/init.lua` | CET bridge that reads a small command file and calls CapriSystem's public API. |
| `mcp/capri-brain.mjs` | Local OpenAI-compatible brain endpoint for Capri's `local` provider. |
| `Iniciar OmniVoice.bat.example` | CPU/CUDA selection example for OmniVoice. |

## CET bridge

Copy the folder to:

```
bin/x64/plugins/cyber_engine_tweaks/mods/CapriMcpBridge/init.lua
```

Restart the game or reload CET. The bridge writes/reads:

```
r6/storages/CapriConstruct/mcp_command.txt
r6/storages/CapriConstruct/mcp_result.txt
```

It only calls public CapriSystem methods (`GetProvider`, `ConnectPlayer2`,
`SetProvider`, `SetApiUrl`, `SetModel`, `TestVoice`, `Summon`, `TestHud`, etc.).
It does not read or return provider keys, and it does nothing outside a loaded
save.

The MCP tools that send those commands are part of the PRAETOR desktop MCP
(`desktop/mcp/capri.mjs`), not this server repository. See
[mcp/README.md](mcp/README.md).

## Brain

`mcp/capri-brain.mjs` exposes an OpenAI-compatible endpoint on
`127.0.0.1:8890`. Capri's **local** provider should point at:

```
http://127.0.0.1:8890/v1
model: capri-brain
```

CapriVoz relays the HTTP request because the game's RedHttpClient only sends to
HTTPS. The brain defaults to local Ollama; it can use Freebuff/OpenAI with a
key supplied only in the local environment. It does not bundle a model.

## Voice

The `.bat.example` is only a template. OmniVoice/CapriVoz binaries, profiles,
models and generated audio are not redistributed. Keep provider keys in the
local CapriVoz/Capri settings and out of version control.
