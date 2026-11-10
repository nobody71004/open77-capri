#!/bin/bash
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

PROD=/opt/open77-xbuniverse
STAGE=/opt/open77-xbuniverse-staging
LOG=/tmp/codeware-fix.log

exec > >(tee -a "$LOG") 2>&1
echo "==> Codeware dependency repair started at $(date -u +%FT%TZ)"

for p in "$PROD" "$STAGE"; do
    test -f "$p/server.jsonc"
done

for p in "$PROD" "$STAGE"; do
    if [ ! -f "$p/server.jsonc.before-codeware-fix" ]; then
        cp -a "$p/server.jsonc" "$p/server.jsonc.before-codeware-fix"
        echo "backup: $p/server.jsonc.before-codeware-fix"
    fi
done

if [ -d "$STAGE/resources/codeware" ] && [ ! -d "$PROD/resources/codeware" ]; then
    cp -a "$STAGE/resources/codeware" "$PROD/resources/codeware"
    echo "copied resources/codeware to production"
fi
test -f "$PROD/resources/codeware/dist/Codeware-1.21.0-open77r1.zip"
test -f "$STAGE/resources/codeware/dist/Codeware-1.21.0-open77r1.zip"

python3 - "$PROD/server.jsonc" "$STAGE/server.jsonc" <<'PY'
import json
import os
import re
import sys

prod_path, stage_path = sys.argv[1:3]

def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()

def commit(path, text):
    json.loads(text)
    temp = path + ".codeware-new"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp, path)

prod = read(prod_path)
match = re.search(r'("load"\s*:\s*\[)(.*?)(\n\s*\])', prod, re.S)
if not match:
    raise SystemExit("production resources.load block not found")
block = match.group(2)
if '"codeware"' not in block:
    if '"archivexl",' not in block:
        raise SystemExit("production archivexl entry not found in resources.load")
    block = block.replace('"archivexl",', '"archivexl",\n      "codeware",', 1)
    prod = prod[:match.start(2)] + block + prod[match.end(2):]
    commit(prod_path, prod)
    print("patched production resources.load with codeware")
else:
    print("production resources.load already contains codeware")

stage = read(stage_path)
if '"id": "codeware-assets"' not in stage:
    match = re.search(r'("packages"\s*:\s*\[)(.*?)(\n\s*\])', stage, re.S)
    if not match:
        raise SystemExit("staging requiredMods.packages block not found")
    block = match.group(2)
    needle = '      {\n        "id": "red-file-system",'
    if needle not in block:
        raise SystemExit("staging red-file-system package anchor not found")
    entry = '''      {
        "id": "codeware-assets",
        "source": "hosted",
        "displayName": "Codeware 1.21.0 (Open77 r1)",
        "version": "1.21.0",
        "sha256": "b4cb49172e3b33f60ba898543d00c017fd5f7fc173464c685f5ec695108a4f6f",
        "sizeBytes": 1966186
      },
'''
    block = block.replace(needle, entry + needle, 1)
    stage = stage[:match.start(2)] + block + stage[match.end(2):]
    commit(stage_path, stage)
    print("patched staging requiredMods with codeware-assets")
else:
    print("staging requiredMods already contains codeware-assets")

for path in (prod_path, stage_path):
    data = json.loads(read(path))
    print(
        path,
        "load_has_codeware=",
        "codeware" in data.get("resources", {}).get("load", []),
        "package_ids=",
        [item.get("id") for item in data.get("requiredMods", {}).get("packages", [])],
    )
PY

restart_unit() {
    unit="$1"
    port="$2"
    echo "==> Restarting $unit"
    systemctl restart "$unit" || true
    for _ in $(seq 1 150); do
        state=$(systemctl is-active "$unit" 2>/dev/null || true)
        code=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/" 2>/dev/null || true)
        if [ "$state" = active ] && [ "$code" = 404 ]; then
            echo "==> $unit active on $port (HTTP $code)"
            return 0
        fi
        sleep 1
    done
    echo "==> ERROR: $unit did not become ready"
    systemctl status "$unit" --no-pager 2>&1 | tail -40 || true
    return 1
}

restart_unit open77-xbuniverse-staging.service 11841
restart_unit open77-xbuniverse.service 11797

echo "==> Final state"
systemctl is-active open77-xbuniverse-staging.service || true
systemctl is-active open77-xbuniverse.service || true
curl -sS --max-time 5 -o /dev/null -w 'prod_http=%{http_code}\n' http://127.0.0.1:11797/ || true
curl -sS --max-time 5 -o /dev/null -w 'staging_http=%{http_code}\n' http://127.0.0.1:11841/ || true
echo "==> Codeware dependency repair complete at $(date -u +%FT%TZ)"
