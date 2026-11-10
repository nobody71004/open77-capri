# Capri brain

`capri-brain.mjs` is a dependency-free Node server that presents an
OpenAI-compatible API to Capri.

It is a **bridge**, not a bundled model. It forwards to:

- **Ollama** by default at `http://127.0.0.1:11434/v1`;
- **Freebuff** at `https://freebuff.com/api/v1/paid` when
  `CAPRI_BRAIN_BACKEND=freebuff` and `OPENAI_API_KEY` is set;
- any OpenAI-compatible endpoint with `CAPRI_BRAIN_BACKEND=openai` and
  `CAPRI_BRAIN_BACKEND_URL`.

## Start

```bash
# local Ollama (default)
CAPRI_BRAIN_BACKEND=ollama \
CAPRI_BRAIN_MODEL=llama3.2:3b \
node client/mcp/capri-brain.mjs

# Freebuff API (key stays local; never commit it)
OPENAI_API_KEY=... \
OPENAI_MODEL=gpt-4o-mini \
CAPRI_BRAIN_BACKEND=freebuff \
node client/mcp/capri-brain.mjs
```

Useful environment variables:

| Variable | Default |
|---|---|
| `CAPRI_BRAIN_PORT` | `8890` |
| `CAPRI_BRAIN_HOST` | `127.0.0.1` |
| `CAPRI_BRAIN_BACKEND` | `ollama` |
| `CAPRI_BRAIN_MODEL` | `llama3.2:3b` (Ollama), `gpt-4o-mini` (Freebuff) |
| `CAPRI_BRAIN_BACKEND_URL` | backend `/v1` URL |
| `CAPRI_BRAIN_MAX_TOKENS` | `260` |
| `CAPRI_BRAIN_TIMEOUT_MS` | `180000` |
| `CAPRI_BRAIN_VISION` | off (images are replaced with a text note) |

Health and model list:

```bash
curl -sS http://127.0.0.1:8890/health
curl -sS http://127.0.0.1:8890/v1/models
```

## Point Capri at it

This is an **admin-machine** setup. The launcher package no longer ships Capri's
F1 CET window, so use the CET bridge and the MCP `capri_configure_provider` tool
from the PRAETOR desktop MCP to set provider/URL/model programmatically:

1. Provider: `local`.
2. URL: `http://127.0.0.1:8890/v1`.
3. Model: `capri-brain`.
4. Save; the game will use CapriVoz's HTTP relay.

On an admin machine that intentionally installs the official CET window
separately, the same values can be entered under
**Connection → On your PC (Ollama, LM Studio)**. That window is not part of the
player package.

## MCP tools

The bridge and brain are included here. The MCP tool definitions that call them
(`capri_provider_status`, `capri_brain_start`, `capri_configure_provider`, etc.)
live in the PRAETOR `desktop/mcp/capri.mjs` integration; they depend on that
MCP host's policy/shell modules and are not duplicated in this server repo.

The CET bridge protocol is deliberately line-based and key-free:

```
id=<unique id>
action=status|connect_player2|set_provider|set_api_url|set_model|...
```

Results are written to `mcp_result.txt` with `ok=1` or `ok=0` and fields such as
`p2State`, `provider`, `model`, `missing`. Provider keys are never read or
returned.
