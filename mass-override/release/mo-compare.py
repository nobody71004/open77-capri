# Compares requiredMods between the production and staging servers, and reports how
# many players each has. Read-only.
import json, re, urllib.request

def strip_jsonc(value):
    out = []; i = 0; quoted = False
    while i < len(value):
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
            while i < len(value) and value[i] != "\n":
                i += 1
            continue
        elif value.startswith("/*", i):
            i = value.index("*/", i) + 2; continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))

def load(root):
    return json.loads(strip_jsonc(open(root + "/server.jsonc", encoding="utf-8").read()))

def players(cfg):
    # The server's own HTTP port: the one whose mod manifest lists Capri. Scanning for the
    # first port that answers finds other servers on this host.
    base = int(cfg["network"]["port"])
    for port in range(base - 12, base + 13):
        try:
            manifest = json.load(urllib.request.urlopen("http://127.0.0.1:%d/mods/v1/manifest" % port, timeout=2))
        except Exception:
            continue
        if not any(m.get("id") == "capri-personality-construct" for m in manifest.get("mods") or []):
            continue
        try:
            body = json.load(urllib.request.urlopen("http://127.0.0.1:%d/query/v1/status" % port, timeout=2))
            return port, body.get("status"), body.get("numplayers"), body.get("name")
        except Exception as e:
            return port, "no query endpoint", str(e)[:80]
    return None

prod = load("/opt/open77-xbuniverse")
print("prod network:", prod.get("network"), "name:", (prod.get("identity") or {}).get("name"))
stag = load("/opt/open77-xbuniverse-staging")
print("staging network:", stag.get("network"), "name:", (stag.get("identity") or {}).get("name"))
def mods(cfg):
    rm = cfg.get("requiredMods") or {}
    if isinstance(rm, dict):
        print("requiredMods keys:", sorted(rm.keys()))
    items = None
    if isinstance(rm, dict):
        for key in ("mods", "required", "packages", "list", "items"):
            if isinstance(rm.get(key), list):
                items = rm.get(key); break
    else:
        items = rm
    return {m.get("id"): (m.get("version"), (m.get("sha256") or "")[:12], m.get("source")) for m in (items or [])}, (rm.get("unsecured") if isinstance(rm, dict) else None)
pm, pu = mods(prod); sm, su = mods(stag)
print("unsecured prod=%s staging=%s" % (pu, su))
for k in sorted(set(pm) | set(sm)):
    a = pm.get(k); b = sm.get(k)
    flag = "same" if a == b else "DIFF"
    print("%-36s %-4s prod=%s staging=%s" % (k, flag, a, b))
print("prod players:", players(prod))
print("staging players:", players(stag))
