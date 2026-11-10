#!/bin/bash
# Move the five Codeware REDscript dependencies into the Capri package.
# Runs as root through the Nexus privileged helper.
set -Eeuo pipefail

NAME=${1:-}
case "$NAME" in
  staging) ROOT=/opt/open77-xbuniverse-staging ;;
  production) ROOT=/opt/open77-xbuniverse ;;
  *) echo "usage: apply-capri-split.sh <staging|production>" >&2; exit 64 ;;
esac

BASE=/tmp/codeware-r2
LOG="$BASE/apply-capri-split-$NAME.log"
mkdir -p "$BASE"
exec > >(tee -a "$LOG") 2>&1

CAPRI_OLD_SHA=263c85dfdde6de37d94068a905e4514221c7457ed82a8e98ab8d47cec46ab244
CAPRI_OLD_VERSION=1.16.0
CAPRI_NEW_VERSION=1.16.1
CAPRI_NEW_FILE=CapriPersonalityConstruct-1.16.1.zip
CODEWARE_OLD_SHA=a7ae8a8d2b19ad41f7cab15a464b7bdffb41996ad212183bcac4e797e1117e4c
CODEWARE_OLD_VERSION=1.21.0-open77r2
CODEWARE_NEW_VERSION=1.21.0-open77r3
CODEWARE_NEW_FILE=Codeware-1.21.0-open77r3.zip
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="$BASE/backup-capri-split-$NAME-$TS"

CAPRI_OLD_BLOB="$ROOT/.open77/mods/$CAPRI_OLD_SHA.blob"
CAPRI_OLD_SIDECAR="$ROOT/.open77/mods/$CAPRI_OLD_SHA.json"
CODEWARE_OLD_BLOB="$ROOT/.open77/mods/$CODEWARE_OLD_SHA.blob"
CODEWARE_OLD_SIDECAR="$ROOT/.open77/mods/$CODEWARE_OLD_SHA.json"
CODEWARE_R2="$ROOT/resources/codeware/dist/Codeware-$CODEWARE_OLD_VERSION.zip"
CODEWARE_R3="$ROOT/resources/codeware/dist/$CODEWARE_NEW_FILE"
SERVER_JSON="$ROOT/server.jsonc"
CODEWARE_LUA="$ROOT/resources/codeware/open77.lua"

echo "==> Capri package split for $ROOT at $TS"
for f in "$CAPRI_OLD_BLOB" "$CAPRI_OLD_SIDECAR" "$CODEWARE_OLD_BLOB" "$CODEWARE_OLD_SIDECAR" "$CODEWARE_R2" "$SERVER_JSON" "$CODEWARE_LUA"; do
  [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done

mkdir -p "$BACKUP"
for f in "$CAPRI_OLD_BLOB" "$CAPRI_OLD_SIDECAR" "$CODEWARE_OLD_BLOB" "$CODEWARE_OLD_SIDECAR" "$CODEWARE_R2" "$SERVER_JSON" "$CODEWARE_LUA"; do
  cp -a "$f" "$BACKUP/$(basename "$f")"
done
echo "backup=$BACKUP"

python3 - "$ROOT" "$NAME" "$CAPRI_OLD_SHA" "$CAPRI_OLD_VERSION" "$CAPRI_NEW_VERSION" "$CAPRI_NEW_FILE" "$CODEWARE_OLD_SHA" "$CODEWARE_OLD_VERSION" "$CODEWARE_NEW_VERSION" "$CODEWARE_NEW_FILE" <<'PY'
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
name = sys.argv[2]
capri_old_sha = sys.argv[3]
capri_old_version = sys.argv[4]
capri_new_version = sys.argv[5]
capri_new_file = sys.argv[6]
codeware_old_sha = sys.argv[7]
codeware_old_version = sys.argv[8]
codeware_new_version = sys.argv[9]
codeware_new_file = sys.argv[10]
now = dt.datetime.now(dt.timezone.utc).isoformat()
base = Path("/tmp/codeware-r2")

capri_blob = root / ".open77/mods" / f"{capri_old_sha}.blob"
capri_sidecar = root / ".open77/mods" / f"{capri_old_sha}.json"
codeware_blob = root / ".open77/mods" / f"{codeware_old_sha}.blob"
codeware_sidecar = root / ".open77/mods" / f"{codeware_old_sha}.json"
codeware_r2 = root / "resources/codeware/dist" / f"Codeware-{codeware_old_version}.zip"
codeware_r3 = root / "resources/codeware/dist" / codeware_new_file
server_json = root / "server.jsonc"
codeware_lua = root / "resources/codeware/open77.lua"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def clone_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    out = zipfile.ZipInfo(info.filename, info.date_time)
    out.compress_type = zipfile.ZIP_DEFLATED
    out.external_attr = info.external_attr
    out.create_system = info.create_system
    out.comment = info.comment
    return out

def install(src: Path, dst: Path) -> None:
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o644)
    os.chown(dst, 0, 0)

for path, expected in ((capri_blob, capri_old_sha), (codeware_r2, codeware_old_sha)):
    got = sha256_file(path)
    if got != expected:
        raise SystemExit(f"unexpected hash for {path}: {got}")

# Build the new Capri zip: original package plus the five Codeware dependency scripts.
capri_tmp = base / f"{capri_new_file}.tmp"
with zipfile.ZipFile(capri_blob, "r") as zin:
    existing = set(zin.namelist())
    with zipfile.ZipFile(capri_tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
        for info in zin.infolist():
            zout.writestr(clone_info(info), zin.read(info.filename))
        with zipfile.ZipFile(codeware_r2, "r") as cz:
            scripts = sorted(n for n in cz.namelist() if n.startswith("r6/scripts/Codeware/") and n.endswith(".reds"))
            if len(scripts) != 5:
                raise SystemExit(f"expected 5 Codeware scripts, found {len(scripts)}: {scripts}")
            for src in scripts:
                target = f"r6/scripts/CapriPersonalityConstruct/Codeware/{Path(src).name}"
                if target in existing:
                    raise SystemExit(f"Capri package already contains {target}")
                zout.writestr(target, cz.read(src))

capri_sha = sha256_file(capri_tmp)
capri_size = capri_tmp.stat().st_size
capri_new_blob = root / ".open77/mods" / f"{capri_sha}.blob"
install(capri_tmp, capri_new_blob)
with zipfile.ZipFile(capri_new_blob, "r") as z:
    capri_count = len([n for n in z.namelist() if not n.endswith("/")])
    if capri_count != 44:
        raise SystemExit(f"new Capri package has {capri_count} files, expected 44")
print(f"capri {capri_old_version} -> {capri_new_version}: {capri_sha} {capri_size} files={capri_count}")

capri_meta = {
    "id": "capri-personality-construct",
    "version": capri_new_version,
    "displayName": "Capri - AI Companion with Voice (LLM)",
    "fileName": capri_new_file,
    "sha256": capri_sha,
    "sizeBytes": capri_size,
    "capability": "executable",
    "fileCount": capri_count,
    "roots": ["archive/pc/mod", "red4ext/plugins", "bin/x64/plugins/cyber_engine_tweaks/mods", "r6/scripts"],
    "importedAtUtc": now,
    "reviewRequestedAtUtc": None,
}
capri_meta_path = root / ".open77/mods" / f"{capri_sha}.json"
capri_meta_path.write_text(json.dumps(capri_meta, indent=2) + "\n", encoding="utf-8")
os.chmod(capri_meta_path, 0o644)
os.chown(capri_meta_path, 0, 0)

# Build the dependency-only Codeware package: no r6/scripts/Codeware files remain.
codeware_tmp = base / f"{codeware_new_file}.tmp"
with zipfile.ZipFile(codeware_r2, "r") as zin:
    kept = [i for i in zin.infolist() if not i.filename.startswith("r6/scripts/Codeware/")]
    with zipfile.ZipFile(codeware_tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
        for info in kept:
            zout.writestr(clone_info(info), zin.read(info.filename))
    if len(kept) != 4:
        raise SystemExit(f"Codeware r3 has {len(kept)} files, expected 4")

codeware_sha = sha256_file(codeware_tmp)
codeware_size = codeware_tmp.stat().st_size
install(codeware_tmp, codeware_r3)
codeware_new_blob = root / ".open77/mods" / f"{codeware_sha}.blob"
install(codeware_tmp, codeware_new_blob)
with zipfile.ZipFile(codeware_new_blob, "r") as z:
    leftovers = [n for n in z.namelist() if n.startswith("r6/scripts/Codeware/")]
    if leftovers:
        raise SystemExit(f"Codeware r3 still contains scripts: {leftovers}")
print(f"codeware {codeware_old_version} -> {codeware_new_version}: {codeware_sha} {codeware_size} files=4")

codeware_meta = {
    "id": "codeware-assets",
    "version": codeware_new_version,
    "displayName": "Codeware 1.21.0 (Open77 r3)",
    "fileName": codeware_new_file,
    "sha256": codeware_sha,
    "sizeBytes": codeware_size,
    "capability": "executable",
    "fileCount": 4,
    "roots": ["red4ext/plugins", "r6/scripts"],
    "importedAtUtc": now,
    "reviewRequestedAtUtc": None,
}
codeware_meta_path = root / ".open77/mods" / f"{codeware_sha}.json"
codeware_meta_path.write_text(json.dumps(codeware_meta, indent=2) + "\n", encoding="utf-8")
os.chmod(codeware_meta_path, 0o644)
os.chown(codeware_meta_path, 0, 0)

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

text = server_json.read_text(encoding="utf-8")
text = patch_package_block(text, "capri-personality-construct", {
    "version": capri_new_version,
    "sha256": capri_sha,
    "sizeBytes": capri_size,
})
text = patch_package_block(text, "codeware-assets", {
    "displayName": "Codeware 1.21.0 (Open77 r3)",
    "version": codeware_new_version,
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

lua_text = codeware_lua.read_text(encoding="utf-8")
lua_text, version_count = re.subn(r'^version\s+"[^"]+"', f'version "{codeware_new_version}"', lua_text, count=1, flags=re.M)
lua_text, preload_count = re.subn(r'^preload_mod\s+"dist/[^"]+"', f'preload_mod "dist/{codeware_new_file}"', lua_text, count=1, flags=re.M)
if version_count != 1 or preload_count != 1:
    raise SystemExit(f"{codeware_lua}: version={version_count} preload={preload_count}")
tmp = codeware_lua.with_name(codeware_lua.name + ".capri-split")
tmp.write_text(lua_text, encoding="utf-8")
os.chmod(tmp, codeware_lua.stat().st_mode & 0o777)
os.chown(tmp, codeware_lua.stat().st_uid, codeware_lua.stat().st_gid)
os.replace(tmp, codeware_lua)
print(f"updated {codeware_lua}")

for old in (capri_blob, capri_sidecar, codeware_blob, codeware_sidecar):
    old.unlink()
    print(f"removed stale {old}")

print("restarting open77-xbuniverse-staging")
subprocess.run(["systemctl", "restart", "open77-xbuniverse-staging"], check=True)
time.sleep(3)
subprocess.run(["systemctl", "is-active", "--quiet", "open77-xbuniverse-staging"], check=True)
print("staging_active=yes")
PY

echo "==> Capri package split for $NAME complete"
