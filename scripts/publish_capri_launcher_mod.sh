#!/bin/bash
# Publish Capri as a launcher-delivered Open77 required mod.
#
# The Open77 Launcher reads /mods/v1/manifest from <game port + 1>, downloads
# every hosted package into its content store, verifies the pinned SHA-256, and
# projects the package's files into the game folder when the player connects.
# This script puts the Capri archive in the server's blob store, adds the
# requiredMods entry, restarts the server (the manifest digest is published at
# startup), and verifies both the manifest and the blob.
#
# Run on the server as root:
#
#   sudo bash scripts/publish_capri_launcher_mod.sh staging \
#        --zip dist/CapriPersonalityConstruct-1.16.1.zip --version 1.16.1
#   sudo bash scripts/publish_capri_launcher_mod.sh production \
#        --zip dist/CapriPersonalityConstruct-1.16.1.zip --version 1.16.1
#
# Capri contains executable content (DLL, .reds, .lua, .ps1). Open77 only
# serves that from an unsecured world, where the launcher names it and asks the
# player before installing. This script refuses to flip `unsecured` itself: an
# operator who has not already accepted that policy must do it deliberately.
#
# The player package must not carry CET UI. This validator accepts only the
# no-UI CapriVozReady heartbeat under cyber_engine_tweaks/mods and refuses
# CapriPersonalityConstruct's window or the admin-only CapriMcpBridge.
set -Eeuo pipefail

NAME=${1:-}
shift || true
ZIP=""
VERSION="1.16.1"
FORCE=0
NO_RESTART=0

usage() {
  echo "usage: $0 <staging|production> --zip PATH [--version X.Y.Z] [--force] [--no-restart]" >&2
  exit 64
}

case "$NAME" in
  staging)
    ROOT=${OPEN77_STAGING_ROOT:-/opt/open77-xbuniverse-staging}
    SERVICE=${OPEN77_STAGING_SERVICE:-open77-xbuniverse-staging.service}
    ;;
  production)
    ROOT=${OPEN77_ROOT:-/opt/open77-xbuniverse}
    SERVICE=${OPEN77_SERVICE:-open77-xbuniverse.service}
    ;;
  *) usage ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --zip) ZIP=${2:-}; shift 2 ;;
    --version) VERSION=${2:-}; shift 2 ;;
    --force) FORCE=1; shift ;;
    --no-restart) NO_RESTART=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown option: $1" >&2; usage ;;
  esac
done

MOD_ID=capri-personality-construct
DISPLAY_NAME="Capri - AI Companion with Voice (LLM)"
SERVER_JSON="$ROOT/server.jsonc"
MODS_DIR="$ROOT/.open77/mods"
BACKUP="$ROOT/server.jsonc.before-capri-launcher-mod"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*"; }

[[ ${EUID} -eq 0 ]] || die "run as root"
[[ -f "$SERVER_JSON" ]] || die "missing $SERVER_JSON"
[[ -n "$ZIP" ]] || die "--zip is required"
[[ -f "$ZIP" ]] || die "zip not found: $ZIP"
command -v python3 >/dev/null || die "python3 is required"
command -v sha256sum >/dev/null || die "sha256sum is required"
[[ -d "$MODS_DIR" ]] || die "missing blob store: $MODS_DIR"

# --- validate the archive before it can reach a player -----------------------
log "Validating $ZIP"
python3 - "$ZIP" <<'PY'
import sys, zipfile
from pathlib import PurePosixPath

roots = (
    "bin/x64/plugins/cyber_engine_tweaks/mods",
    "red4ext/plugins",
    "bin/x64/plugins",
    "archive/pc/mod",
    "r6/scripts",
    "r6/tweaks",
    "r6/input",
    "r6/config",
    "engine/config",
    "engine/tools",
    "EasyAntiCheat",
    "mods",
    "bin/x64",
)
required = (
    "archive/pc/mod/CapriPersonalityConstruct.archive",
    "red4ext/plugins/CapriPersonalityConstruct/CapriPersonalityConstruct.dll",
    "bin/x64/plugins/cyber_engine_tweaks/mods/CapriVozReady/init.lua",
)

def normalize(name):
    path = name.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.strip("/")

def root_of(path):
    for root in roots:
        if path == root or path.startswith(root + "/"):
            return root
    return None

def traversal(path):
    if not path or path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return True
    return any(part in ("", ".", "..") for part in PurePosixPath(path).parts)

with zipfile.ZipFile(sys.argv[1]) as archive:
    names = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = normalize(info.filename)
        if traversal(name):
            raise SystemExit(f"refusing traversal entry: {info.filename}")
        if root_of(name) is None:
            raise SystemExit(f"refusing {info.filename}: outside every Open77 mod root")
        lower = name.lower()
        if lower.startswith("r6/storages/"):
            raise SystemExit(f"refusing {info.filename}: player storage")
        if "/cache/" in lower:
            raise SystemExit(f"refusing {info.filename}: generated cache")
        if lower.endswith("/config.json") and "/caprivoz/" in lower:
            raise SystemExit(f"refusing {info.filename}: per-user CapriVoz config")
        if lower.endswith((".log", "db.sqlite3")) or ".before-" in lower:
            raise SystemExit(f"refusing {info.filename}: local runtime state")
        names.append(name)
missing = [name for name in required if name not in names]
if missing:
    raise SystemExit("archive is missing " + ", ".join(missing))
if not any(n.startswith("r6/scripts/CapriPersonalityConstruct/") and n.endswith(".reds") for n in names):
    raise SystemExit("archive has no Capri redscript files")
cet_root = "bin/x64/plugins/cyber_engine_tweaks/mods/"
cet_ready = "bin/x64/plugins/cyber_engine_tweaks/mods/CapriVozReady/"
cet_files = [n for n in names if n.startswith(cet_root)]
extra_cet = [n for n in cet_files if not n.startswith(cet_ready)]
if extra_cet:
    raise SystemExit(
        "refusing player-facing CET UI entries: " + ", ".join(sorted(extra_cet))
    )
print(f"    {len(names)} files, all rooted")
PY

SHA=$(sha256sum "$ZIP" | awk '{print $1}')
SIZE=$(stat -c '%s' "$ZIP")
BLOB="$MODS_DIR/$SHA.blob"
SIDECAR="$MODS_DIR/$SHA.json"
log "sha256=$SHA size=$SIZE"

# --- refuse to restart on a populated server without --force -----------------
if [[ "$FORCE" -ne 1 && "$NO_RESTART" -ne 1 && -f "$ROOT/server.log" ]]; then
  ONLINE=$(python3 - "$ROOT/server.log" <<'PY'
import re, sys
try:
    lines = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
except OSError:
    print(0); raise SystemExit
start = max([i for i, line in enumerate(lines) if "Server configuration:" in line] or [0])
live = {}
for line in lines[start:]:
    match = re.search(r"Connection (\d+) (opened|closed)", line)
    if match:
        live[match.group(1)] = match.group(2) == "opened"
print(sum(1 for value in live.values() if value))
PY
)
  if [[ "$ONLINE" != "0" ]]; then
    die "$ONLINE player connection(s) are open; rerun with --force to restart and disconnect them, or --no-restart to stage without publishing the digest"
  fi
fi

# --- store the blob + sidecar ------------------------------------------------
install -m 0644 "$ZIP" "$BLOB"
python3 - "$SIDECAR" "$SHA" "$SIZE" "$VERSION" "$ZIP" <<'PY'
import datetime as dt, json, os, sys
sidecar, sha, size, version, archive = sys.argv[1:6]
data = {
    "id": "capri-personality-construct",
    "version": version,
    "displayName": "Capri - AI Companion with Voice (LLM)",
    "fileName": os.path.basename(archive),
    "sha256": sha,
    "sizeBytes": int(size),
    "capability": "executable",
    "importedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "reviewRequestedAtUtc": None,
}
with open(sidecar, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
os.chmod(sidecar, 0o644)
PY
log "stored $BLOB"

# --- add or update requiredMods.packages ------------------------------------
[[ -f "$BACKUP" ]] || { cp -a "$SERVER_JSON" "$BACKUP"; log "backup $BACKUP"; }

python3 - "$SERVER_JSON" "$SHA" "$SIZE" "$VERSION" "$MOD_ID" "$DISPLAY_NAME" <<'PY'
import json, os, re, sys

server_json, sha, size, version, mod_id, display_name = sys.argv[1:7]
text = open(server_json, encoding="utf-8").read()

def strip_jsonc(value: str) -> str:
    out, i, n, quoted = [], 0, len(value), False
    while i < n:
        c = value[i]
        if quoted:
            out.append(c)
            if c == "\\":
                out.append(value[i + 1]); i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True; out.append(c)
        elif value.startswith("//", i):
            while i < n and value[i] != "\n":
                i += 1
            continue
        elif value.startswith("/*", i):
            i = value.index("*/", i) + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))

def object_span(value: str, key: str) -> tuple[int, int]:
    match = re.search(r'"' + re.escape(key) + r'"\s*:\s*\{', value)
    if not match:
        raise SystemExit(f'"{key}" object not found')
    start = value.index("{", match.start())
    depth, quoted, escaped = 0, False, False
    for i in range(start, len(value)):
        c = value[i]
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f'"{key}" object is not closed')

data = json.loads(strip_jsonc(text))
required = data.get("requiredMods")
if not isinstance(required, dict):
    raise SystemExit("server.jsonc has no requiredMods section")
if required.get("unsecured") is not True:
    raise SystemExit(
        "requiredMods.unsecured is not true. Capri ships executable content, so the launcher "
        "will refuse it from a secure world. Set unsecured deliberately (or get the exact bytes "
        "reviewed) before publishing."
    )

start, end = object_span(text, "requiredMods")
block = text[start:end]
if re.search(r'"enabled"\s*:\s*false', block):
    block = re.sub(r'("enabled"\s*:\s*)false', r"\1true", block, count=1)
    text = text[:start] + block + text[end:]
    required = json.loads(strip_jsonc(text)).get("requiredMods")

# canonical entry, indented like the surrounding array
entry_body = (
    '{\n'
    '  "id": "%s",\n'
    '  "source": "hosted",\n'
    '  "displayName": "%s",\n'
    '  "version": "%s",\n'
    '  "sha256": "%s",\n'
    '  "sizeBytes": %s\n'
    '}' % (mod_id, display_name, version, sha, size)
)

block_match = re.search(r'([ \t]*)\{\s*"id"\s*:\s*"' + re.escape(mod_id) + r'"[\s\S]*?\n[ \t]*\}', text)
if block_match:
    indent = block_match.group(1)
    rendered = entry_body.replace("\n", "\n" + indent)
    text = text[:block_match.start()] + indent + rendered + text[block_match.end():]
else:
    req_match = re.search(r'"requiredMods"\s*:\s*\{', text)
    pkg_match = re.search(r'"packages"\s*:\s*\[', text[req_match.end():]) if req_match else None
    if not pkg_match:
        raise SystemExit("requiredMods.packages array not found")
    open_at = req_match.end() + pkg_match.end()
    empty = re.match(r"\s*\]", text[open_at:]) is not None
    indent_match = re.search(r'\n([ \t]*)$', text[:open_at])
    indent = indent_match.group(1) if indent_match else "      "
    separator = "" if empty else ","
    rendered = entry_body.replace("\n", "\n" + indent)
    text = text[:open_at] + "\n" + indent + rendered + separator + text[open_at:]

json.loads(strip_jsonc(text))
temporary = server_json + ".capri-launcher-mod"
with open(temporary, "w", encoding="utf-8") as handle:
    handle.write(text)
os.chmod(temporary, os.stat(server_json).st_mode & 0o777)
os.chown(temporary, os.stat(server_json).st_uid, os.stat(server_json).st_gid)
os.replace(temporary, server_json)
print("    requiredMods.packages updated")
PY

log "patching complete"

if [[ "$NO_RESTART" -eq 1 ]]; then
  log "skipped restart; the manifest digest is published only at server startup"
  exit 0
fi

# --- restart and verify ------------------------------------------------------
log "Restarting $SERVICE"
systemctl restart "$SERVICE"
for _ in $(seq 1 180); do
  if systemctl is-active --quiet "$SERVICE"; then
    break
  fi
  sleep 2
done
systemctl is-active --quiet "$SERVICE" || {
  systemctl status --no-pager -l "$SERVICE" | tail -60 >&2 || true
  die "$SERVICE did not become active"
}

log "Verifying the launcher manifest and blob"
python3 - "$SERVER_JSON" "$SHA" "$SIZE" "$MOD_ID" <<'PY'
import hashlib, json, re, sys, time, urllib.request, urllib.error

server_json, sha, size, mod_id = sys.argv[1:5]
text = open(server_json, encoding="utf-8").read()

def strip_jsonc(value: str) -> str:
    out, i, n, quoted = [], 0, len(value), False
    while i < n:
        c = value[i]
        if quoted:
            out.append(c)
            if c == "\\":
                out.append(value[i + 1]); i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True; out.append(c)
        elif value.startswith("//", i):
            while i < n and value[i] != "\n":
                i += 1
            continue
        elif value.startswith("/*", i):
            i = value.index("*/", i) + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))

config = json.loads(strip_jsonc(text))
port = int((config.get("network") or {}).get("port") or 0)
if port <= 0:
    raise SystemExit("server.jsonc has no network.port")
manifest_url = f"http://127.0.0.1:{port + 1}/mods/v1/manifest"

last = None
for _ in range(60):
    try:
        manifest = json.load(urllib.request.urlopen(manifest_url, timeout=5))
        break
    except Exception as error:  # noqa: BLE001 -- startup is still settling
        last = error
        time.sleep(2)
else:
    raise SystemExit(f"manifest did not answer at {manifest_url}: {last}")

entry = next((m for m in manifest.get("mods") or [] if m.get("id") == mod_id), None)
if entry is None:
    raise SystemExit(f"manifest has no '{mod_id}' entry: {json.dumps(manifest)[:600]}")
if entry.get("sha256") != sha or int(entry.get("sizeBytes") or 0) != int(size):
    raise SystemExit(f"manifest entry does not match the published blob: {json.dumps(entry)}")
if entry.get("source") != "hosted":
    raise SystemExit(f"manifest entry is not hosted: {json.dumps(entry)}")

lines = "".join(
    f"{m['id']}\x1f{(m.get('version') or m.get('minVersion') or '').lower()}\x1f{m.get('sha256') or ''}\n"
    for m in sorted(manifest.get("mods") or [], key=lambda item: item["id"])
)
digest = hashlib.sha256(lines.encode("utf-8")).hexdigest()
if manifest.get("digest") != digest:
    raise SystemExit("manifest digest does not match its packages")
if manifest.get("enabled") is not True:
    raise SystemExit("manifest is disabled")
if manifest.get("unsecured") is False:
    raise SystemExit("manifest is not unsecured; executable packages cannot be served")

blob_url = f"http://127.0.0.1:{port + 1}/mods/v1/blobs/{sha}"
try:
    payload = urllib.request.urlopen(blob_url, timeout=30).read()
except urllib.error.HTTPError as error:
    raise SystemExit(f"blob endpoint returned HTTP {error.code}")
actual = hashlib.sha256(payload).hexdigest()
if actual != sha:
    raise SystemExit(f"blob endpoint served {actual}, expected {sha}")

print(f"    manifest: {manifest_url}")
print(f"    entry: {mod_id} v{entry.get('version')} {sha[:12]}… {size} bytes")
print(f"    digest: {digest}")
print(f"    blob: {len(payload)} bytes, hash verified")
PY

log "Capri is now a launcher-delivered required mod on $NAME"
