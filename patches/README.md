# Capri clinic chip

These are the exact snippets added by `scripts/patch_capri_clinic.py`. They are
kept here for review and for manual recovery; the patcher is the source of
truth and is idempotent.

| File | Change |
|---|---|
| `resources/opx_infinity/config/ripperdoc.lua` | `CATALOG` entry |
| `resources/opx_infinity/modules/ripperdoc/module.lua` | `RP_SOLD` guard |
| `resources/opx_infinity/modules/ripperdoc/locales.lua` | EN/FR name, grade, description |

The chip is an inventory item. It does not summon Capri; the client companion
mod does. See [../docs/CLIENT_SETUP.md](../docs/CLIENT_SETUP.md).
