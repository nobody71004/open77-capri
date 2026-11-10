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
- Open **F1 → Appearance → Show on HUD**. This forces a visual test without an
  LLM.
- **Take her outside** for the body.
- Confirm the Capri archive is present:
  `archive/pc/mod/CapriPersonalityConstruct.archive`.
- Confirm the RED4ext plugin and CET mod loaded; check the RED4ext/CET logs.
- Check `settings.json` has `hud: true`.
- If no F1 window opens, CET itself is not drawing; fix CET before debugging
  Capri.

## Capri is visible but does not talk

- She needs a provider. Open **F1 → Connection**.
- Player2: connect through the app or browser device flow. An empty
  `player2_respuesta.json` and `player2Key` means no session.
- Gemini/OpenAI/OpenRouter: set the key and model in the same tab.
- Local: ensure Ollama/LM Studio is running and the URL/model are correct.
- CapriVoz being alive only means her **voice** is ready; it does not generate
  dialogue. `voz_latido.json` updating is not proof that an LLM is connected.
- Check `GetMissingSetup()`/the red warning in the Connection tab.

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
