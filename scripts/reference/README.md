# Pinned reference scripts

These are the exact package operations used on our Open77 server. They are
included for reproducibility, not as a universal installer.

Pinned inputs:

- Capri `1.16.0` → `1.16.1`
- Codeware `1.21.0-open77r2` → `1.21.0-open77r3`

Before running anything:

1. Read the constants at the top of each script.
2. Confirm the server root, package IDs, old SHA-256 values and blob names.
3. Back up `.open77/mods`, `server.jsonc`, `resources/codeware/open77.lua` and
   the service units.
4. Run `diagnose_capri_package.sh` first; it is read-only.
5. Run staging, verify with a staging client, then production.

`apply_capri_split.sh` and `apply_production_split.sh` delete stale `.blob` and
`.json` files after creating backups. They are intentionally strict and fail
when the expected hashes or paths do not match. Do not “fix” a failure by
deleting the checks.

`fix_codeware.sh` adds the Codeware asset package and `resources.load` entry
when the install is missing them; it also restarts both units. Adapt it if your
unit names or package ID differ.

These scripts do not include Capri, Codeware or any other third-party package.
They only manipulate the packages you already imported into Open77.
