import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile

SHA = sys.argv[1]
VERSION = "1.16.15"
MOD_ID = "capri-personality-construct"
SERVER = "/opt/open77-xbuniverse/server.jsonc"


def strip_jsonc(value):
    out = []
    i = 0
    quoted = False
    while i < len(value):
        c = value[i]
        if quoted:
            out.append(c)
            if c == "\\":
                out.append(value[i + 1])
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            out.append(c)
        elif value.startswith("//", i):
            while i < len(value) and value[i] != "\n":
                i += 1
            continue
        elif value.startswith("/*", i):
            i = value.index("*/", i) + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


config = json.loads(strip_jsonc(open(SERVER, encoding="utf-8").read()))
base = int(config["network"]["port"])

port = None
manifest = None
for candidate in range(base - 12, base + 13):
    try:
        probe = urllib.request.urlopen(f"http://127.0.0.1:{candidate}/mods/v1/manifest", timeout=2)
        body = json.load(probe)
    except Exception:
        continue
    if any(m.get("id") == MOD_ID for m in body.get("mods") or []):
        port = candidate
        manifest = body
        break
assert port, "no local port served a manifest containing " + MOD_ID
print("manifest port:", port)

entry = next((m for m in manifest["mods"] if m.get("id") == MOD_ID), None)
print("manifest entry:", json.dumps(entry))
assert entry, "capri entry missing from manifest"
assert entry["sha256"] == SHA, "manifest sha mismatch"
assert entry["version"] == VERSION, "manifest version mismatch"
assert manifest.get("unsecured") is not False, "manifest not unsecured"

payload = urllib.request.urlopen(f"http://127.0.0.1:{port}/mods/v1/blobs/{SHA}", timeout=120).read()
print("blob bytes:", len(payload), "sha ok:", hashlib.sha256(payload).hexdigest() == SHA)
assert hashlib.sha256(payload).hexdigest() == SHA, "blob sha mismatch"

with zipfile.ZipFile(io.BytesIO(payload)) as z:
    names = z.namelist()
    open77 = z.read("r6/scripts/Open77/Open77MassOverride.reds").decode("utf-8")
    capri = z.read("r6/scripts/CapriPersonalityConstruct/Capri.MassOverride.reds").decode("utf-8")
    print("entries:", len(names))
    print("build:", re.search(r'Version\(\) -> String \{ return "([^"]+)"', open77).group(1))
    print("glitch:", "ActionQuestStartGlitch" in open77)
    print("strobe:", "ActionSetDeviceON" in open77)
    print("cars accelerate:", "VehicleNetrunnerQuickhackType.Accelerate" in open77)
    print("ink:", "GetWorldWidgets()" in open77, "lights:", "SetParameters(settings" in open77, "fx:", "transition_glitch_loop" in open77)
    print("panic:", "gamedataStimType.Terror" in open77)
    print("gate:", "production" if ("duckdns.org/mass-override/" in open77 and "mass-override-staging" not in open77) else "STAGING")
    assert "mass-override-staging" not in open77, "production build still points at the staging gate"
    print("cb handlers:", open77.count("cb func OnReply"))
    print("self re-arms:", len(re.findall(r"DelayCallback\(this,", open77)))
print("VERIFIED")
