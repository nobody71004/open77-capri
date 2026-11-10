# Server installation

## Prerequisites

- Linux Open77 server with systemd.
- Root access and a maintenance window.
- Python **3.10+**.
- Backups of the three clinic files and `server.jsonc`.
- The Capri client package and Codeware packages already imported into Open77
  for the client side (or use the package-split reference).
- A test character whose chrome you can inspect and remove.

The installer changes only:

```
resources/opx_infinity/config/ripperdoc.lua
resources/opx_infinity/modules/ripperdoc/module.lua
resources/opx_infinity/modules/ripperdoc/locales.lua
```

It creates `*.before-capri-chip` backups once and is idempotent. It does not
touch `server.jsonc`; in particular it does **not** enable `unsecured`.

## 1. Review the patch as a dry run

From the repository root on the server:

```bash
python3 scripts/patch_capri_clinic.py \
  --root /opt/open77-xbuniverse \
  --out /tmp/capri-clinic-preview
```

Inspect the three files under `/tmp/capri-clinic-preview`. The patch adds:

- the `capri_personality_construct` entry at the end of `CATALOG`;
- `if entry.RP_SOLD == true then return false end` after the existing `rp`
  guard in `module.lua`;
- three EN and three FR locale keys after the two `ripperdoc.item.deck`
  anchors.

If a locale anchor or the `rp` guard is missing, stop. Do not force the patch.

## 2. Install on staging

```bash
cp .env.example .env
# edit values if your paths/unit names differ
sudo OPEN77_ROOT=/opt/open77-xbuniverse-staging \
     OPEN77_SERVICE=open77-xbuniverse-staging.service \
     bash scripts/install_capri_clinic.sh
sudo OPEN77_ROOT=/opt/open77-xbuniverse-staging \
     OPEN77_SERVICE=open77-xbuniverse-staging.service \
     bash scripts/verify_capri_clinic.sh
```

The install script restarts the unit you name, waits up to 60 seconds, and
prints the unit status if it fails. It never restarts a different unit.

## 3. Test on staging

Use a test character at the clinic:

1. Open the ripperdoc catalogue.
2. Confirm the chip is in the **Operating System** section, grade
   **Prototype**, price **2500**.
3. Buy it, equip it in the OS slot, and confirm the server ledger records the
   purchase and wear.
4. Remove it, re-equip it, and confirm there are no combat stats and no
   duplicate entries.
5. Check the Open77 logs and the client Redscript log; there should be no new
   script errors.

Only after staging passes should production be changed.

## 4. Install on production

```bash
sudo OPEN77_ROOT=/opt/open77-xbuniverse \
     OPEN77_SERVICE=open77-xbuniverse.service \
     bash scripts/install_capri_clinic.sh
sudo OPEN77_ROOT=/opt/open77-xbuniverse \
     OPEN77_SERVICE=open77-xbuniverse.service \
     bash scripts/verify_capri_clinic.sh
```

Do not set `unsecured=true` as part of this change. If your server already has
an unsecured listener, put it behind a firewall/VPN and treat this patch as
unrelated to that exposure.

## 5. Package split

The clinic chip works without the package split. The split is for clients that
need Capri's Redscript dependencies distributed without duplicate Codeware
definitions. Follow [PACKAGE_SPLIT.md](PACKAGE_SPLIT.md) separately, staging
first.

## 6. Rollback

See [ROLLBACK.md](ROLLBACK.md). The clinic backups are next to the patched
files; the package split has a timestamped backup directory.
