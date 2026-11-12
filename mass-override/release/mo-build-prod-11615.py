# The PRODUCTION package of 1.16.15: the staging build with its gate pointed at the
# production gate (https://xyberrp.duckdns.org/mass-override/, open77-mass-override on
# 11901) and the feed labelled "production". Nothing else changes; the checks below
# prove it.
import hashlib, os, zipfile

SRC = "CapriPersonalityConstruct-1.16.15-massoverride-street.zip"
OUT = "CapriPersonalityConstruct-1.16.15-massoverride-street-prod.zip"
TARGET = "r6/scripts/Open77/Open77MassOverride.reds"
STAGING = "https://xyberrp.duckdns.org/mass-override-staging/"
PRODUCTION = "https://xyberrp.duckdns.org/mass-override/"
LABEL_OLD = 'public static func Label() -> String { return "staging"; }'
LABEL_NEW = 'public static func Label() -> String { return "production"; }'

os.chdir("/root/capri-publish")
with zipfile.ZipFile(SRC) as zin:
    entries = {i.filename.replace("\\", "/"): zin.read(i) for i in zin.infolist() if not i.is_dir()}
before = dict(entries)
text = entries[TARGET].decode("utf-8")
if text.count(STAGING) != 4:
    raise SystemExit("expected 4 staging gate URLs, found %d" % text.count(STAGING))
if text.count(LABEL_OLD) != 1:
    raise SystemExit("feed label not found")
text = text.replace(STAGING, PRODUCTION).replace(LABEL_OLD, LABEL_NEW)
entries[TARGET] = text.encode("utf-8")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
    for name in sorted(entries):
        info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o644 << 16
        zout.writestr(info, entries[name])

raw = open(OUT, "rb").read()
with zipfile.ZipFile(OUT) as z:
    after = {n: z.read(n) for n in z.namelist()}
    open77 = after[TARGET].decode("utf-8")
changed = [n for n in after if after[n] != before.get(n)]
checks = {
    "same entries": sorted(after) == sorted(before),
    "only the gate script changed": changed == [TARGET],
    "no staging gate left": "mass-override-staging" not in open77,
    "4 production gate URLs": open77.count(PRODUCTION) == 4,
    "feed labelled production": LABEL_NEW in open77,
    "build 1.16.15": 'Version() -> String { return "1.16.15"; }' in open77,
}
for k, v in checks.items():
    print(("ok      " if v else "MISSING ") + k)
if not all(checks.values()):
    raise SystemExit("content check failed")
print("sha256", hashlib.sha256(raw).hexdigest())
print("size", len(raw))
print("BUILT")
