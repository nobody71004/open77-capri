# The server-brain kit

Capri's launcher package (`requiredMods`) cannot carry `r6/storages/CapriConstruct/settings.json`: the
launcher refuses player storage. So a player's Capri starts on her default provider, Player2, and without
the Player2 app she greets with *"I'm here, V, but disconnected"*, even when the game server's machine runs
a brain for her.

This kit adds one script to a server's Capri package, `r6/scripts/CapriPersonalityConstruct/Capri.ServerBrain.reds`
([template](template/Capri.ServerBrain.reds)). When Capri reads her settings at game start, it points her
`local` provider at the brain nginx serves on the server's machine (`https://HOST/capri-brain-…/v1`, model
`capri-brain`), unless the player has a service of their own with its own key. Its decision is written to
`r6/storages/CapriConstruct/server_brain.json` on the player's PC, without any address or key.

| File | What it does |
| --- | --- |
| `capri_kit.py` | Runs on the owner's PC (the fivem2open77 Studio's Python and SSH settings, through `av_kit.py`): `check`, `voice`, `gate --role`, `publish --role staging\|production`, `verify`, `putback`, `player`, `guard`. |
| `capri_wire.py` | The build: the live package plus the script, reproducible, checked against Capri's own `Capri.Storage.reds`. Hook `patch` (one call where `LoadSettings` returns) is the one REDscript 1.0 compiles; `wrap` (`@wrapMethod(CapriStorage) LoadSettings`) is refused by REDscript 1.0 preview.22 for a scripted class's method and only tried second. It also ships the 12 Capri scripts REDscript 1.0 migrates at every start, as this PC's game migrated them, when they differ from the package's by nothing but those edits (`is_migration_of`, whose counts match the game's own log). |
| `capri_scc.py` | The game's own Redscript compiler (`engine/tools/scc_lib.dll`) on a sandbox: the game's pristine bundle, this PC's scripts with the package's Capri, and copies of the scripts the game's RED4ext plugins add (from the game's own last compile log). The live package (migrated) must compile first, then the new one, both with nothing to migrate; a window the compiler opens is closed with Cancel at once. |
| `remote/capri_server.py` | On the game servers' machine: `look` (read only), `fetch`, `import` (the hosted store and `server.jsonc`, compare-and-swap on the live sha256, refused with players on, `--check-config`, a record for the put-back), `verify`, `putback`, `guard` (per-address `limit_req`/`limit_conn` on the brain's nginx location: kept first, `nginx -t`, reload, the brain asked again, put back on any failure; refused when the brain's requests all come from loopback or private addresses), `guard-putback`. |
| `remote/capri_voice_server.py` | Her own voice on the game servers' machine (1.16.17): Pocket TTS 4.0.1 with her voice states from the package (`voces/capri_<language>.safetensors`), the engine and model revisions a player's local engine runs. `POST /v1/audio/speech {input, language}` -> WAV, one line at a time, a bounded queue answered 503 when full, one log line per request (never the text). `--selftest` says one line per language. `capri_server.py voice` installs it (venv, pinned pip installs, self-test, its own user and unit, an nginx location with its own private path and `limit_req`), idempotent. |
| `capri_voz.py` | Capri Voz using that voice: `servidor.json` added, `CapriVoz.ps1` and `linux/capri_voz_linux.py` edited by exact anchored edits that undo exactly (a package already edited is taken back first): "auto" = local engine, else the server's voice, else Windows'; fallbacks; the heartbeat says `server` so the game stops asking for a local install; a file log `cache/capri_voz.log`. PowerShell's own parser checks the edited file on the owner's PC before anything is sent. |
| `capri_keys.py` | Her five keys as Open77 key mappings (2026-11-12): one anchored edit to `Capri.System.reds` -- `CapriSystem.KeyFromHost(game, action, down)` (static) and `OnHostKey(action, down)` -- which the XyberRP resource `opx_infinity` (`core/client/caprikeys.lua`) calls through `Open77.rtti` for every press of the five mappings it declares under ESC > Settings > KEY BINDINGS (type to her, mark, talk, summon, switch seats). While that resource keeps her lease (asked every 2 s, good for 6 s) her own reading of the game's keys rests, so the key a player sets there is the only one; a game nobody asks for has her own keys back within 6 s. The edit sits between marks and comes out exactly; `publish` puts it in every build. |
| `capri_mo.py`, `template/mass-override/`, `remote/gate/` | Mass Override for every player (1.16.17): the repo's two scripts with the server's own gate put in, and the gate (`gate.js`, `dev-server.js`: sessions, positions, `GET /casts`) that `capri_server.py gate` installs (kept first, restarted, asked locally and through nginx, put back on failure). |
| `bats/*.bat.in` | The owner's bats; `@@HOST@@` becomes the HOST line of their own kits when the kit is delivered. |
| `tests/` | `python3 kit/tests/test_kit.py`: the build, the migration check, the machine's side against a fake machine (two server folders, stand-ins for nginx, curl and systemctl, each server's manifest port), the kit's flow, the bats. `rehearse_publish.py`: `publish` on the owner's PC with everything real (the game's compiler, the brain over HTTPS) but the machine, which a folder stands in for. |

The brain's address is a capability: none of these files contains it, and no log line prints its path
(`capri-brain-<secret>`). It does travel inside the package to every player who joins, which is why `guard`
limits how often one address may ask the brain; `check` reports whether it does.

Checked on the real compiler (REDscript 1.0.0-preview.22, the owner's PC, 2026-11-12): the live 1.16.15 Capri
scripts as packaged give 1554 errors and a migration request; migrated, 107 files compile with 603 warnings and
0 errors; with `Capri.ServerBrain.reds` and the patch, 108 files, 603 warnings, 0 errors; the wrap gives
"could not find a method with a matching signature".
With her keys for Open77 (`capri_keys.py`, 1.16.18 on XyberRP Staging, 1.16.19 on XyberRP): 108 files, 603
warnings, 0 errors. A live client's `Open77.rtti.resolve` finds her instance methods by their short name but
not the static `KeyFromHost`, so `caprikeys.lua` also tries its decorated names and her system's `OnHostKey`.
