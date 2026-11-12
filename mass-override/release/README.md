# Mass Override release scripts

The exact scripts used to build, publish and check Capri 1.16.15 on XyberRP Staging
and XyberRP. They run on the game-server host from `/root/capri-publish`, next to the
previous package zip and the two scripts from `game/r6/scripts`.

| Script | What it does |
| --- | --- |
| `mo-build-11615.py` | Builds the staging package: the previous package with `Capri.MassOverride.reds` and `Open77MassOverride.reds` swapped in, then content checks (build number, every lever, no storage reopened, both HTTP handlers `cb`, both HTTP objects re-armed). |
| `mo-build-prod-11615.py` | Builds the production package from the staging one: only the gate base changes (`/mass-override-staging/` -> `/mass-override/`) and the feed label; the checks prove nothing else did. |
| `mo-import.py` / `mo-import-prod.py` | Import a package into the server's hosted mod store (`.open77/mods/<sha>.blob` + `.json`) and point the `capri-personality-construct` entry of `requiredMods.packages` at it. Only version, sha256 and sizeBytes change; `server.jsonc` is backed up as `server.jsonc.before-capri-<version>`. The production one refuses to run without `--yes-production`. Restart the server afterwards. |
| `mo-verify-11615.py` / `mo-verify-prod-11615.py` | After the restart: the server's manifest names the new sha and version, the blob it serves hashes to that sha, and the scripts inside are the expected build (the production check fails if the staging gate is still named). |
| `mo-compare.py` | Read-only: `requiredMods` of both servers side by side, and each server's player count from its own query endpoint (the one whose manifest lists Capri; other servers share the host). |
| `mo-gate-prod.sh` | Sets up the production gate beside the staging one (`../deploy`): `/opt/open77-mass-override`, `open77-mass-override.service` on 11901, nginx `location /mass-override/`. Idempotent; nginx is backed up to `/root` and restored if `nginx -t` fails. |
| `mo-gate-check.sh` | Polls both gates' feeds and posts a `deploy-check` report to each over the public URLs, then shows each report in its own gate's log. |
