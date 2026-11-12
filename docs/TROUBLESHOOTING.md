# Troubleshooting

## The chip is not in the clinic

1. Run `scripts/verify_capri_clinic.sh`.
2. Confirm the service was restarted after the patch.
3. Check the server root you patched is the one the unit actually uses.
4. Confirm the client is connected to that server, not a different staging or
   production endpoint.
5. Confirm `RP_SOLD = true` and the `entry.RP_SOLD == true` guard are both
   present. The catalogue entry alone is not enough if the unsold filter
   rejects `rp` items.
6. Check EN/FR locale keys; a missing key should show a raw key, not remove the
   item.

## The chip exists but buying/equipping fails

- Check the server console/ledger for capacity, tier, funds or slot errors.
- Confirm `SLOT = 'operating_system'` and `SYSTEM = 'operating_system'`.
- Confirm the character has an OS slot available and no conflicting chrome.
- Do not test on a production character unless you can remove the item and
  restore the ledger.

## Redscript duplicate symbols / Codeware redefinitions

This is the package split problem. Read [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md).
Check the client package contains the five Codeware scripts under the Capri
folder and the Codeware package contains none of them. Confirm the new hashes
and sizes in `server.jsonc` and `open77.lua`.

## Capri is invisible

- Step out of the ripperdoc/clinic menu; Capri suppresses keys and HUD in menus.
- The player package has **no Capri CET window**. On an admin machine that
  installed the official window separately, use
  **F1 → Appearance → Show on HUD** to force a visual test without an LLM; on a
  normal player install, set `hud: true` in
  `r6/storages/CapriConstruct/settings.json` and reload the save.
- **Take her outside** for the body (admin CET window only).
- Confirm the Capri archive is present:
  `archive/pc/mod/CapriPersonalityConstruct.archive`.
- Confirm the RED4ext plugin and the no-UI `CapriVozReady` resource loaded; check
  the RED4ext/CET logs.
- Check `settings.json` has `hud: true`.

## Capri is visible but does not talk

- **"I'm here, V, but disconnected"** on a player's PC: she is on Player2, her
  default, because the package does not say where the server's brain is. The
  launcher cannot ship `settings.json`; a package built with the server-brain kit
  ([kit/README.md](../kit/README.md)) carries `Capri.ServerBrain.reds`, which points
  her at the brain nginx serves on the server's machine when the game starts.
  Its decision is in `r6/storages/CapriConstruct/server_brain.json` on that PC;
  RedHttpClient's log (`red4ext/logs/redhttpclient-*.log`) shows her requests.
- She needs a provider. The player package has no CET Connection tab; configure
  it on the admin machine through `CapriMcpBridge` or the separately installed
  official CET window, then check the resulting
  `r6/storages/CapriConstruct/settings.json`.
- Player2: connect through the app or browser device flow. An empty
  `player2_respuesta.json` and `player2Key` means no session.
- Gemini/OpenAI/OpenRouter: set the key and model on the admin machine; never
  put provider keys in the player package.
- Local: ensure Ollama/LM Studio is running and the URL/model are correct.
- CapriVoz being alive only means her **voice** is ready; it does not generate
  dialogue. `voz_latido.json` updating is not proof that an LLM is connected.
- Check `GetMissingSetup()` through the admin bridge, or the `missing` field in
  `mcp_result.txt`.

## No voice

- Check CapriVoz health at `http://localhost:4325/health`.
- Check OmniVoice at `http://127.0.0.1:8880/v1/models`.
- While Cyberpunk is running, OmniVoice should use CPU to preserve VRAM; CUDA
  can be used when the game is closed.
- The optional `capri-brain.mjs` is an LLM brain, not a TTS engine; it does not
  replace CapriVoz/OmniVoice.
- The WAV test clips from development are not part of the in-game voice path.

## Local brain / bridge

- `Capri CET bridge did not answer` means the game is closed, no save is
  loaded, or `CapriMcpBridge` is not installed/loaded yet.
- `Capri Brain` health on `127.0.0.1:8890` but the game cannot answer means the
  CapriVoz relay or the saved provider is wrong.
- If switching from Ollama to Freebuff/OpenAI, stop and restart the brain so the
  backend changes; the MCP `capri_configure_provider` tool handles this when the
  PID file is present.
- Freebuff/OpenAI backend without a key returns an authentication error from
  the provider; the key is not in this repository.
