# Imports a Capri build into the STAGING server's hosted mod store and points the
# capri-personality-construct requiredMods entry at it. Only that entry's version,
# sha256 and sizeBytes change; server.jsonc is backed up first.
import datetime, hashlib, json, os, re, shutil, sys

ZIP, VERSION = sys.argv[1], sys.argv[2]
MOD_ID = "capri-personality-construct"
ROOT = "/opt/open77-xbuniverse-staging"
MODS = ROOT + "/.open77/mods"
SERVER = ROOT + "/server.jsonc"

raw = open(ZIP, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
size = len(raw)
blob = os.path.join(MODS, sha + ".blob")
meta = os.path.join(MODS, sha + ".json")
if not os.path.exists(blob):
    shutil.copyfile(ZIP, blob)
assert hashlib.sha256(open(blob, "rb").read()).hexdigest() == sha, "blob copy mismatch"

text = open(SERVER, encoding="utf-8").read()
i = text.index('"id": "' + MOD_ID + '"')
j = text.index("}", i)
block = text[i:j]
name = re.search(r'"displayName": "([^"]*)"', block).group(1)
doc = {
    "id": MOD_ID,
    "version": VERSION,
    "displayName": name,
    "fileName": os.path.basename(ZIP),
    "sha256": sha,
    "sizeBytes": size,
    "capability": "executable",
    "importedAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "reviewRequestedAtUtc": None,
}
with open(meta, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")

new = re.sub(r'"version": "[^"]*"', '"version": "%s"' % VERSION, block, count=1)
new = re.sub(r'"sha256": "[0-9a-f]{64}"', '"sha256": "%s"' % sha, new, count=1)
new = re.sub(r'"sizeBytes": \d+', '"sizeBytes": %d' % size, new, count=1)
backup = SERVER + ".before-capri-" + VERSION
if not os.path.exists(backup):
    shutil.copyfile(SERVER, backup)
if new != block:
    open(SERVER, "w", encoding="utf-8").write(text[:i] + new + text[j:])
print("entry:", new.replace("\n", " "))
print("sha256", sha, "size", size)
print("IMPORTED")
