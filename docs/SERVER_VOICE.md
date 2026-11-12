# Capri's own voice for every player (the server voice)

Capri Voz (the helper next to the RED4ext plugin that speaks for Capri) says her lines with her real voice only
when the player's PC installed her local engine: "Install local voice" puts a private Python, PyTorch for the CPU,
Pocket TTS and faster-whisper (about 900 MB) into `%LOCALAPPDATA%\CapriVoz\motor`, and `capri_motor.py` loads her
voice states (`CapriVoz/voces/capri_<language>.safetensors`). Every other PC fell back to a borrowed Windows voice
(on Linux, to no voice), and the launcher package no longer ships the F1 window with that button.

## What runs on the server

`kit/remote/capri_voice_server.py`: the same engine with the same voice states, as a small HTTP service.

- Pocket TTS **4.0.1** with torch **2.15.0** for the CPU: the exact versions a player's local engine had on the
  owner's laptop (2026-11-12), so the English and Spanish models are the same revisions
  (`kyutai/pocket-tts-without-voice-cloning`, `english` a7056f50..., `spanish` 1e08e6a2...). The voice states load
  without the voice-cloning weights; nothing gated is downloaded.
- `POST /v1/audio/speech {"input", "language", "voice": "capri", "response_format": "wav"}` -> 24 kHz mono 16-bit
  WAV, headers `X-Capri-Voice` (`capri`, or the catalog voice used for a language she has no state for),
  `X-Capri-Seconds`, `X-Capri-Generated-Ms`. `GET /health` names the languages loaded and counts lines, errors,
  refusals and the average time to make one.
- One line at a time (Pocket TTS is not thread-safe), on 2-4 threads; up to 12 wait, at most 25 s each, then 503 at
  once so the player's Capri Voz uses its own fallback instead of hanging. Lines up to 1200 characters.
- One log line per request: status, language, length, wait, generation time, seconds of audio, voice, bytes --
  never the text; the player's address only as a short hash.
- `capri_server.py voice` installs it: `/opt/capri-voice` (a venv from the system Python 3.10-3.14 with venv, or the
  standalone CPython 3.11.18 Capri Voz for Linux uses, hash checked), her voice states from the live package, a
  self-test in each language (its WAVs in `/opt/capri-voice/selftest`), its own system user, `capri-voice.service`
  (Nice 5, CPUWeight 50, MemoryMax 3G, offline Hugging Face cache, read-only but for that cache; without the
  sandbox options on a machine that refuses mount namespaces), and an nginx location next to the brain's with its
  own private path (`/capri-voice-<secret>/`, kept in `/root/capri-kit/voice.json`, 0600) and `limit_req` 40 r/m
  burst 20 per address. nginx is kept first, `nginx -t`, reloaded, asked through, and put back on any failure.
  Nothing is done when it is all there and answering.

## What the package carries

`kit/capri_voz.py`:

- `CapriVoz/servidor.json`: where the server's voice answers, the world, the package version, the languages.
- `CapriVoz.ps1` (Windows) and `linux/capri_voz_linux.py` (Proton), edited by exact anchored edits that undo
  exactly: provider `"auto"` (the default) is her local engine when installed, else the server's voice (unless it
  failed in the last minute), else Windows' voice; a line whose voice fails is said by the next one in that order;
  the heartbeat tells the game `server` while the server's voice speaks for "auto", so her greeting no longer asks
  for a local install; every Capri Voz message also goes to `CapriVoz/cache/capri_voz.log`. Version 18, so an older
  Capri Voz still running is replaced at the next start.

## Checked

- The server code on Linux with the pinned versions (cloud, catalog voices): queueing, 503 when full, 400/413.
- Her real voice states with that code and the laptop's own engine: English 4.6 s and Spanish 3.7 s of audio,
  voice `capri`.
- The edited `CapriVoz.ps1` on the owner's laptop (Windows PowerShell 5.1), driven through the game's own file
  protocol (`voz_pedido.json` -> `voz_respuesta.json`) against that server: `proveedor: server`, her voice in English
  (with the robot effect) and Spanish, heartbeat `server`; with the server gone, the line said by Windows' voice and
  the heartbeat back to `auto`; a minute later her server voice again.
- The edited Linux Capri Voz against the server (cloud): "auto" -> server, the robot effect, the failure path.
- PowerShell's own parser on the edited file, inside the kit's rehearsal of `publish`.
