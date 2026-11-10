# Capri + Codeware package split

## Why

In the versions used on our server, Capri's client package and the Codeware
package both provided the same five `r6/scripts/Codeware/*.reds` dependencies.
Redscript sees both copies and can fail with duplicate symbol/redefinition
errors.

The fix has two halves:

1. **Capri** gets the five Codeware dependency scripts inside its package.
2. **Codeware** becomes dependency-only: the five `r6/scripts/Codeware/*.reds`
   files are removed from its zip, while its DLL/other assets remain.

The package IDs and blobs change, so Open77's `server.jsonc` and
`resources/codeware/open77.lua` must be updated to the new hashes and sizes.

## Pinned versions used by the reference scripts

- Capri: `1.16.0` → `1.16.1`
- Codeware: `1.21.0-open77r2` → `1.21.0-open77r3`

The scripts in `scripts/reference/` are the exact implementation used on our
server. They contain the old/new hashes and versions. **Do not run them blindly
on a different package set.** Check the constants, the package IDs, the blob
paths and the service names first.

## Reference files

| File | Purpose |
|---|---|
| `scripts/reference/fix_codeware.sh` | Adds the Codeware asset package and `resources.load` entry when missing; exact hash/size. |
| `scripts/reference/apply_capri_split.sh` | Builds the new Capri and Codeware zips on staging, writes metadata, updates `server.jsonc` and `open77.lua`, removes stale blobs, restarts staging. |
| `scripts/reference/apply_production_split.sh` | Copies the already-verified staging blobs to production and updates production metadata. |
| `scripts/reference/diagnose_capri_package.sh` | Read-only inventory of package blobs, hashes, sidecars and references. |

## Safe procedure

1. Back up the server root and `.open77/mods`; the scripts also create a
   timestamped backup directory under `/tmp/codeware-r2`.
2. Run `diagnose_capri_package.sh` and confirm the old Capri/Codeware SHAs and
   paths match the script constants.
3. If Codeware assets are missing, run `fix_codeware.sh` first and confirm both
   units are active.
4. Run `apply_capri_split.sh staging`. It validates the old hashes, builds the
   new zips, checks the file counts, updates metadata and restarts staging.
5. Have a staging client run the package preflight and load a save. Check
   `r6/logs/redscript_rCURRENT.log` for **0 errors** and confirm Capri's
   archive/DLL/CET files are present.
6. Only then run `apply_production_split.sh`; it copies the exact staging
   blobs and restarts production.
7. Verify the new package IDs, versions, hashes and sizes in `server.jsonc` and
   `resources/codeware/open77.lua`.

## What the scripts are not

- They are not a general Open77 package manager.
- They do not download third-party mods.
- They do not remove player data or database rows.
- They are not safe to run twice without checking the current hashes; the
  scripts intentionally fail when paths or hashes do not match.
