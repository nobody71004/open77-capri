#!/bin/bash
# Apply the verified Capri/Codeware split to production.
# Runs as root through the Nexus privileged helper.
set -Eeuo pipefail

STAGING=/opt/open77-xbuniverse-staging
ROOT=/opt/open77-xbuniverse
BASE=/tmp/codeware-r2
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="$BASE/backup-capri-split-production-$TS"
LOG="$BASE/apply-capri-split-production.log"
mkdir -p "$BASE"
exec > >(tee -a "$LOG") 2>&1

CAPRI_OLD_SHA=263c85dfdde6de37d94068a905e4514221c7457ed82a8e98ab8d47cec46ab244
CAPRI_NEW_SHA=0cf90ea5997e43b8bfd03911e508ba885fb222aeb52a3ff2695b8c233206a76e
CAPRI_NEW_VERSION=1.16.1
CODEWARE_OLD_SHA=a7ae8a8d2b19ad41f7cab15a464b7bdffb41996ad212183bcac4e797e1117e4c
CODEWARE_NEW_SHA=007eb0ea14e928762c5bce0e288b592f83d707cf89ff28ab8c91f3ab596fbdea
CODEWARE_NEW_VERSION=1.21.0-open77r3
CODEWARE_NEW_FILE=Codeware-1.21.0-open77r3.zip

PROD_CAPRI_OLD_BLOB="$ROOT/.open77/mods/$CAPRI_OLD_SHA.blob"
PROD_CAPRI_OLD_SIDECAR="$ROOT/.open77/mods/$CAPRI_OLD_SHA.json"
PROD_CODEWARE_OLD_BLOB="$ROOT/.open77/mods/$CODEWARE_OLD_SHA.blob"
PROD_CODEWARE_OLD_SIDECAR="$ROOT/.open77/mods/$CODEWARE_OLD_SHA.json"
STAGING_CAPRI_BLOB="$STAGING/.open77/mods/$CAPRI_NEW_SHA.blob"
STAGING_CAPRI_SIDECAR="$STAGING/.open77/mods/$CAPRI_NEW_SHA.json"
STAGING_CODEWARE_BLOB="$STAGING/.open77/mods/$CODEWARE_NEW_SHA.blob"
STAGING_CODEWARE_SIDECAR="$STAGING/.open77/mods/$CODEWARE_NEW_SHA.json"
STAGING_CODEWARE_R3="$STAGING/resources/codeware/dist/$CODEWARE_NEW_FILE"
PROD_CODEWARE_R3="$ROOT/resources/codeware/dist/$CODEWARE_NEW_FILE"
SERVER_JSON="$ROOT/server.jsonc"
CODEWARE_LUA="$ROOT/resources/codeware/open77.lua"

echo "==> Production Capri split at $TS"
for f in "$PROD_CAPRI_OLD_BLOB" "$PROD_CAPRI_OLD_SIDECAR" "$PROD_CODEWARE_OLD_BLOB" "$PROD_CODEWARE_OLD_SIDECAR" "$STAGING_CAPRI_BLOB" "$STAGING_CAPRI_SIDECAR" "$STAGING_CODEWARE_BLOB" "$STAGING_CODEWARE_SIDECAR" "$STAGING_CODEWARE_R3" "$SERVER_JSON" "$CODEWARE_LUA"; do
  [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done

mkdir -p "$BACKUP"
for f in "$PROD_CAPRI_OLD_BLOB" "$PROD_CAPRI_OLD_SIDECAR" "$PROD_CODEWARE_OLD_BLOB" "$PROD_CODEWARE_OLD_SIDECAR" "$SERVER_JSON" "$CODEWARE_LUA"; do
  cp -a "$f" "$BACKUP/$(basename "$f")"
done
echo "backup=$BACKUP"

# Copy the exact packages already exercised by the staging client preflight.
cp -a "$STAGING_CAPRI_BLOB" "$ROOT/.open77/mods/$CAPRI_NEW_SHA.blob"
cp -a "$STAGING_CAPRI_SIDECAR" "$ROOT/.open77/mods/$CAPRI_NEW_SHA.json"
cp -a "$STAGING_CODEWARE_BLOB" "$ROOT/.open77/mods/$CODEWARE_NEW_SHA.blob"
cp -a "$STAGING_CODEWARE_SIDECAR" "$ROOT/.open77/mods/$CODEWARE_NEW_SHA.json"
cp -a "$STAGING_CODEWARE_R3" "$PROD_CODEWARE_R3"

python3 - "$ROOT" "$CAPRI_NEW_VERSION" "$CAPRI_NEW_SHA" "$CODEWARE_NEW_VERSION" "$CODEWARE_NEW_SHA" "$CODEWARE_NEW_FILE" <<'PY'
from pathlib import Path
import json
import os
import re
import sys

root = Path(sys.argv[1])
capri_version = sys.argv[2]
capri_sha = sys.argv[3]
codeware_version = sys.argv[4]
codeware_sha = sys.argv[5]
codeware_file = sys.argv[6]
capri_size = (root / ".open77/mods" / f"{capri_sha}.blob").stat().st_size
codeware_size = (root / ".open77/mods" / f"{codeware_sha}.blob").stat().st_size

def patch_package_block(text: str, package_id: str, fields: dict[str, object]) -> str:
    pattern = re.compile(r'(\{\s*"id"\s*:\s*"' + re.escape(package_id) + r'"[\s\S]*?\n\s*\})')
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"could not find package block {package_id}")
    block = match.group(1)
    for key, value in fields.items():
        if isinstance(value, int):
            block, count = re.subn(r'("' + re.escape(key) + r'"\s*:\s*)\d+', lambda m: m.group(1) + str(value), block, count=1)
        else:
            block, count = re.subn(r'("' + re.escape(key) + r'"\s*:\s*")[^"]*(")', lambda m: m.group(1) + str(value) + m.group(2), block, count=1)
        if count != 1:
            raise SystemExit(f"{package_id}: replaced {key} {count} times")
    return text[:match.start(1)] + block + text[match.end(1):]

server_json = root / "server.jsonc"
text = server_json.read_text(encoding="utf-8")
text = patch_package_block(text, "capri-personality-construct", {
    "version": capri_version,
    "sha256": capri_sha,
    "sizeBytes": capri_size,
})
text = patch_package_block(text, "codeware-assets", {
    "displayName": "Codeware 1.21.0 (Open77 r3)",
    "version": codeware_version,
    "sha256": codeware_sha,
    "sizeBytes": codeware_size,
})
json.loads(text)
tmp = server_json.with_name(server_json.name + ".capri-split")
tmp.write_text(text, encoding="utf-8")
os.chmod(tmp, server_json.stat().st_mode & 0o777)
os.chown(tmp, server_json.stat().st_uid, server_json.stat().st_gid)
os.replace(tmp, server_json)
print(f"updated {server_json}")

codeware_lua = root / "resources/codeware/open77.lua"
lua_text = codeware_lua.read_text(encoding="utf-8")
lua_text, version_count = re.subn(r'^version\s+"[^"]+"', f'version "{codeware_version}"', lua_text, count=1, flags=re.M)
lua_text, preload_count = re.subn(r'^preload_mod\s+"dist/[^"]+"', f'preload_mod "dist/{codeware_file}"', lua_text, count=1, flags=re.M)
if version_count != 1 or preload_count != 1:
    raise SystemExit(f"{codeware_lua}: version={version_count} preload={preload_count}")
tmp = codeware_lua.with_name(codeware_lua.name + ".capri-split")
tmp.write_text(lua_text, encoding="utf-8")
os.chmod(tmp, codeware_lua.stat().st_mode & 0o777)
os.chown(tmp, codeware_lua.stat().st_uid, codeware_lua.stat().st_gid)
os.replace(tmp, codeware_lua)
print(f"updated {codeware_lua}")
PY

for old in "$PROD_CAPRI_OLD_BLOB" "$PROD_CAPRI_OLD_SIDECAR" "$PROD_CODEWARE_OLD_BLOB" "$PROD_CODEWARE_OLD_SIDECAR"; do
  rm -f "$old"
  echo "removed stale $old"
done

echo "restarting open77-xbuniverse"
systemctl restart open77-xbuniverse
sleep 3
systemctl is-active --quiet open77-xbuniverse
echo "production_active=yes"
