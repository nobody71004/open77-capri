"""The Capri kit's tests: the build (capri_wire), the machine's side (remote/capri_server.py against a fake machine:
two server folders, nginx/curl/systemctl stand-ins, each server's manifest port), the kit's own flow (capri_kit.py
publish / verify / putback with the machine reached through the same files instead of SSH, the compiler stood in
for), and the bats.  Run: python3 kit/tests/test_kit.py"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
sys.path.insert(0, HERE)
import capri_wire as W  # noqa: E402
import fakes  # noqa: E402

REMOTE = os.path.join(KIT, "remote", "capri_server.py")
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    if not cond:
        print(f"FAIL {name} {detail}")


def entries(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


# ------------------------------------------------------------------------------------------------ the build
def test_build():
    old = fakes.package()
    data, rep = W.build(old, fakes.URL, fakes.HOST, "XyberRP Staging", "1.16.16", "wrap")
    e, o = entries(data), entries(old)
    check("wrap: one file more", len(e) == len(o) + 1, f"{len(e)} vs {len(o)}")
    check("wrap: only the new script changed", rep["changed"] == [W.TARGET], rep["changed"])
    check("wrap: Capri.Storage.reds byte for byte", e[W.STORAGE] == o[W.STORAGE])
    for n in o:
        if n != W.STORAGE:
            check(f"wrap: {n} unchanged", e[n] == o[n])
    v = W.wired_values(e[W.TARGET])
    check("wrap: script values", v == {"Package": "1.16.16", "World": "XyberRP Staging", "Url": fakes.URL,
                                       "Host": fakes.HOST, "Model": "capri-brain", "hook": "wrap"}, v)
    text = e[W.TARGET].decode()
    check("wrap: the address once", text.count(fakes.URL) == 1)
    check("wrap: no placeholder left", "@@" not in text)
    check("wrap: hooks LoadSettings", "@wrapMethod(CapriStorage)\nprivate func LoadSettings() -> ref<CapriSettingsDTO> {"
          in text and "wrappedMethod()" in text and "CapriServerBrain.Wire(this, s);" in text)
    check("wrap: module Capri", re.search(r"^module Capri$", text, re.M) is not None)
    check("wrap: report hides the address", fakes.SECRET not in json.dumps(rep))
    data2, rep2 = W.build(old, fakes.URL, fakes.HOST, "XyberRP Staging", "1.16.16", "wrap")
    check("wrap: reproducible (same bytes twice)", data2 == data and rep2["sha256"] == rep["sha256"])
    check("wrap: zip entries sorted, fixed time", [i.filename for i in zipfile.ZipFile(io.BytesIO(data)).infolist()]
          == sorted(e) and all(i.date_time == W.FIXED_TIME for i in zipfile.ZipFile(io.BytesIO(data)).infolist()))
    check("wrap: already wired is seen", W.already_wired(e, fakes.URL) and not W.already_wired(o, fakes.URL))

    # patch
    data, rep = W.build(old, fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "patch")
    e = entries(data)
    check("patch: storage and script changed", rep["changed"] == sorted([W.TARGET, W.STORAGE]), rep["changed"])
    st = e[W.STORAGE].decode()
    check("patch: one call, before return s", st.count(W.PATCH_MARK) == 1 and
          "CapriServerBrain.Wire(this, s);\n        return s;\n    }\n\n    public func SaveSettings()" in st)
    check("patch: script has no wrap", "@wrapMethod" not in e[W.TARGET].decode())
    check("patch: hook named", W.wired_values(e[W.TARGET])["hook"] == "patch")
    # patch -> wrap: the patch taken out again
    data3, rep3 = W.build(data, fakes.URL, fakes.HOST, "XyberRP", "1.16.17", "wrap")
    e3 = entries(data3)
    check("patch then wrap: Capri.Storage.reds back to Capri's own", e3[W.STORAGE] == entries(old)[W.STORAGE])
    check("patch then wrap: report says what it had", rep3["had"].get("hook") == "patch" and
          rep3["had"].get("Url") == "the same address", rep3["had"])
    # patch again on a patched package: still one call
    data4, _ = W.build(data, fakes.URL, fakes.HOST, "XyberRP", "1.16.17", "patch")
    check("patch twice: still one call", entries(data4)[W.STORAGE].decode().count(W.PATCH_MARK) == 1)
    # CRLF storage keeps CRLF
    oldc = fakes.package(crlf=True)
    datac, _ = W.build(oldc, fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "patch")
    stc = entries(datac)[W.STORAGE].decode()
    check("patch: CRLF file stays CRLF", "\r\n" in stc and "\n" not in stc.replace("\r\n", ""))
    datacw, repcw = W.build(oldc, fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "wrap")
    check("wrap: CRLF storage untouched", entries(datacw)[W.STORAGE] == entries(oldc)[W.STORAGE])
    # a wired package with another address: replaced
    other = "https://xyberrp.duckdns.org/capri-brain-ffffffffffffffffffff/v1"
    d1, _ = W.build(old, other, fakes.HOST, "XyberRP", "1.16.16", "wrap")
    d2, r2 = W.build(d1, fakes.URL, fakes.HOST, "XyberRP", "1.16.17", "wrap")
    check("another address replaced", W.wired_values(entries(d2)[W.TARGET])["Url"] == fakes.URL and
          r2["had"]["Url"] == "another address")


POSE = (b"module Capri\n\nenum CapriPose {\n    Stand = 0,\n    Sit = 1\n}\n\npublic struct CapriPoseData {\n"
        b"    let a: Float;\n}\n\npublic class CapriPoses {\n    public static func All() -> array<CapriPoseData> {\n"
        b"        return [new CapriPoseData(1.0), new CapriPoseData(2.0)];\n    }\n"
        b"    public static func One() -> ref<CapriPoses> {\n        return new CapriPoses();\n    }\n}\n")
POSE_MIGRATED = POSE.replace(b"new CapriPoseData(", b"CapriPoseData(").replace(b"enum CapriPose {", b"public enum CapriPose {")
POSE_PATH = "r6/scripts/CapriPersonalityConstruct/Capri.PoseData.reds"


def test_migration():
    check("migration: 3 edits seen", W.is_migration_of(POSE, POSE_MIGRATED) == 3, W.is_migration_of(POSE, POSE_MIGRATED))
    check("migration: the same file is none", W.is_migration_of(POSE, POSE) == 0)
    check("migration: another change is none", W.is_migration_of(POSE, POSE_MIGRATED.replace(b"2.0", b"3.0")) == 0)
    check("migration: a new line is none", W.is_migration_of(POSE, POSE_MIGRATED + b"\n") == 0)
    check("migration: an added new is none", W.is_migration_of(POSE_MIGRATED, POSE) == 0)
    old = fakes.package(extra={POSE_PATH: POSE})
    game = {POSE_PATH: POSE_MIGRATED, W.STORAGE: entries(old)[W.STORAGE],
            "r6/scripts/CapriPersonalityConstruct/Capri.System.reds": b"module Capri\npublic class CapriSystem { }\n"}
    data, rep = W.build(old, fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "wrap", game=game)
    e = entries(data)
    check("migration: the migrated file shipped", e[POSE_PATH] == POSE_MIGRATED)
    check("migration: report", rep["migrated"] == {POSE_PATH: 3} and rep["other_version_here"] ==
          ["r6/scripts/CapriPersonalityConstruct/Capri.System.reds"], rep)
    check("migration: another version here kept as packaged", e["r6/scripts/CapriPersonalityConstruct/Capri.System.reds"]
          == entries(old)["r6/scripts/CapriPersonalityConstruct/Capri.System.reds"])
    check("migration: changed = migrated + script", rep["changed"] == sorted([POSE_PATH, W.TARGET]), rep["changed"])
    base, done, other = W.migrated_only(old, game)
    check("migration: baseline has it, no script", entries(base)[POSE_PATH] == POSE_MIGRATED and W.TARGET not in entries(base))
    base2, done2, _ = W.migrated_only(old, {})
    check("migration: nothing here, baseline is the live bytes", base2 == old and done2 == {})
    data2, rep2 = W.build(data, fakes.URL, fakes.HOST, "XyberRP", "1.16.17", "wrap", game=game)
    check("migration: a migrated package needs none again", rep2["migrated"] == {} and
          entries(data2)[POSE_PATH] == POSE_MIGRATED)


def test_refusals():
    old = fakes.package()

    def refused(name, fn):
        try:
            fn()
        except W.BuildError as e:
            check(f"refused: {name}", True, str(e))
            check(f"refusal hides the address: {name}", fakes.SECRET not in str(e))
            return
        check(f"refused: {name}", False, "built anyway")

    refused("http address", lambda: W.build(old, fakes.URL.replace("https", "http"), fakes.HOST, "XyberRP", "1.16.16", "wrap"))
    refused("no /v1", lambda: W.build(old, fakes.URL[:-3], fakes.HOST, "XyberRP", "1.16.16", "wrap"))
    refused("host mismatch", lambda: W.build(old, fakes.URL, "other.example", "XyberRP", "1.16.16", "wrap"))
    refused("quote in the world", lambda: W.build(old, fakes.URL, fakes.HOST, 'Xy"ber', "1.16.16", "wrap"))
    refused("bad version", lambda: W.build(old, fakes.URL, fakes.HOST, "XyberRP", "1.16.x", "wrap"))
    refused("no such hook", lambda: W.build(old, fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "inject"))
    no_load = fakes.STORAGE_REDS.replace("private func LoadSettings() -> ref<CapriSettingsDTO> {",
                                         "private func LoadAll() -> ref<CapriSettingsDTO> {")
    refused("Capri changed LoadSettings", lambda: W.build(fakes.package(storage=no_load), fakes.URL, fakes.HOST, "XyberRP",
                                                          "1.16.16", "wrap"))
    no_anchor = fakes.STORAGE_REDS.replace("        return s;\n    }\n\n    public func SaveSettings()",
                                           "        return s;\n    }\n\n    public func SaveAll()")
    refused("patch anchor moved", lambda: W.build(fakes.package(storage=no_anchor), fakes.URL, fakes.HOST, "XyberRP",
                                                  "1.16.16", "patch"))
    data, _ = W.build(fakes.package(storage=no_anchor), fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "wrap")
    check("wrap does not need the patch anchor", W.TARGET in entries(data))
    refused("player storage in the package", lambda: W.build(fakes.package(extra={
        "r6/storages/CapriConstruct/settings.json": b"{}"}), fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "wrap"))
    refused("a path outside the mod roots", lambda: W.build(fakes.package(extra={"r6/cache/x.bin": b"1"}), fakes.URL,
                                                            fakes.HOST, "XyberRP", "1.16.16", "wrap"))
    refused("not a zip", lambda: W.build(b"not a zip", fakes.URL, fakes.HOST, "XyberRP", "1.16.16", "wrap"))
    no_storage = entries(old)
    del no_storage[W.STORAGE]
    refused("no Capri.Storage.reds", lambda: W.build(W.write_zip(no_storage), fakes.URL, fakes.HOST, "XyberRP",
                                                     "1.16.16", "wrap"))
    check("bump", W.bump("1.16.15") == "1.16.16" and W.bump("1.16.9") == "1.16.10" and W.bump("2.0") == "2.1")
    check("mask", W.mask(f"see {fakes.URL} now") == "see https://xyberrp.duckdns.org/capri-brain-<secret>/v1 now")


# ------------------------------------------------------------------------------------------------ the machine
def remote(machine, *args, work=None):
    work = work or tempfile.mkdtemp(dir=machine.base)
    p = subprocess.run([sys.executable, REMOTE, args[0], work] + list(args[1:]), capture_output=True, text=True,
                       env=machine.env(), timeout=120)
    out = p.stdout + p.stderr
    res = {}
    for line in out.splitlines():
        if line.startswith("CAPRI-RESULT "):
            res = json.loads(line[len("CAPRI-RESULT "):])
    return p.returncode, out, res, work


def no_secrets(name, out):
    check(f"{name}: no brain path printed", fakes.SECRET not in out)
    check(f"{name}: no address printed", not re.search(r"\b203\.0\.113\.\d+|\b198\.51\.100\.\d+", out))
    check(f"{name}: no key printed", "supersecretvalue" not in out)
    lines = [l for l in out.splitlines() if l.strip()]
    check(f"{name}: every line is a CAPRI line", all(l.startswith("CAPRI") for l in lines),
          [l for l in lines if not l.startswith("CAPRI")][:3])


def test_remote():
    m = fakes.FakeMachine()
    try:
        code, out, res, _ = remote(m, "look")
        check("look: exit 0", code == 0, out[-800:])
        no_secrets("look", out)
        check("look: both servers", [r.get("role") for r in res.get("roles", [])] == ["staging", "production"])
        check("look: not wired yet", "the brain is NOT wired in" in out)
        check("look: brain found, limits named", "per-address limits: limit_req OFF" in out and
              "xyberrp.duckdns.org/capri-brain-<secret>/" in out, out[:1500])
        check("look: the models through nginx", "capri-brain, qwen2.5:7b" in out)
        check("look: access log counted without addresses", '2 request(s) to the brain, answers {"200": 2}, from 2 address(es)'
              in out, [l for l in out.splitlines() if "request(s)" in l])
        check("look: Ollama models", "Ollama: active; models: qwen2.5:7b" in out)
        check("look: manifest seen", "the manifest players get (port 23841): Capri 1.16.15, the same build" in out,
              [l for l in out.splitlines() if "manifest" in l])

        code, out, res, work = remote(m, "fetch", "--role", "staging")
        check("fetch: exit 0", code == 0, out[-800:])
        no_secrets("fetch", out)
        url = open(os.path.join(work, "brain.url")).read().strip()
        check("fetch: brain.url is the address", url == fakes.URL)
        check("fetch: brain.url 0600", (os.stat(os.path.join(work, "brain.url")).st_mode & 0o777) == 0o600)
        live = open(os.path.join(work, "capri-current.zip"), "rb").read()
        check("fetch: the live package", live == m.packages["staging"])
        check("fetch: result", res.get("entry", {}).get("version") == "1.16.15" and res.get("wired") is False and
              res.get("online") == 0 and res.get("host") == fakes.HOST, res)

        new, rep = W.build(live, url, fakes.HOST, "XyberRP Staging", "1.16.16", "wrap")
        z = os.path.join(work, "new.zip")
        open(z, "wb").write(new)
        old_entry = m.entry("staging")

        # players on: nothing changes
        m.set_online("staging", ["7"])
        code, out, res, _ = remote(m, "import", "--role", "staging", "--zip", z, "--version", "1.16.16",
                                   "--expect-sha", old_entry["sha256"], work=work)
        check("import with a player on: exit 3", code == 3, out[-600:])
        check("import with a player on: server.jsonc untouched", m.entry("staging") == old_entry)
        m.set_online("staging", [])
        # the live build changed meanwhile: nothing changes
        code, out, res, _ = remote(m, "import", "--role", "staging", "--zip", z, "--version", "1.16.16",
                                   "--expect-sha", "b" * 64, work=work)
        check("import after a change: exit 3", code == 3 and res.get("why") == "the live build changed", res)
        # check-config refuses: put back
        open(os.path.join(m.root("staging"), "check-config-exit"), "w").write("1")
        code, out, res, _ = remote(m, "import", "--role", "staging", "--zip", z, "--version", "1.16.16",
                                   "--expect-sha", old_entry["sha256"], work=work)
        check("import refused by --check-config: exit 1, put back", code == 1 and m.entry("staging") == old_entry, out[-600:])
        open(os.path.join(m.root("staging"), "check-config-exit"), "w").write("0")
        before_text = open(os.path.join(m.root("staging"), "server.jsonc")).read()
        code, out, res, _ = remote(m, "import", "--role", "staging", "--zip", z, "--version", "1.16.16",
                                   "--expect-sha", old_entry["sha256"], work=work)
        check("import: exit 0", code == 0, out[-800:])
        no_secrets("import", out)
        e = m.entry("staging")
        check("import: entry names the build", e == {"version": "1.16.16", "sha256": rep["sha256"], "sizeBytes": len(new)}, e)
        after_text = open(os.path.join(m.root("staging"), "server.jsonc")).read()
        check("import: comments and the rest of server.jsonc kept", after_text.count("//") == before_text.count("//")
              and "/* required mods: the launcher installs them */" in after_text and
              after_text.replace(rep["sha256"], old_entry["sha256"]).replace('"1.16.16"', '"1.16.15"')
              .replace(str(len(new)), str(old_entry["sizeBytes"])) == before_text)
        blob = os.path.join(m.root("staging"), ".open77", "mods", rep["sha256"] + ".blob")
        check("import: blob in the store", open(blob, "rb").read() == new)
        side = json.load(open(blob[:-5] + ".json"))
        check("import: sidecar", side.get("sha256") == rep["sha256"] and side.get("version") == "1.16.16" and
              side.get("capability") == "executable" and side.get("displayName"), side)
        check("import: backup kept", any(f.startswith("server.jsonc.before-capri-kit-1.16.16-")
                                         for f in os.listdir(m.root("staging"))))
        check("import: production untouched", m.entry("production")["version"] == "1.16.15")
        rec = json.load(open(os.path.join(m.state, "staging.json")))
        check("import: record", rec["history"][-1]["from"] == old_entry, rec)

        # verify before the restart: the manifest still hands out the old build
        code, out, res, _ = remote(m, "verify", "--role", "staging", "--sha", rep["sha256"], "--version", "1.16.16")
        check("verify before the restart: fails", code == 1 and not res.get("ok"), out[-600:])
        m.restart("staging")
        code, out, res, _ = remote(m, "verify", "--role", "staging", "--sha", rep["sha256"], "--version", "1.16.16")
        check("verify after the restart: ok", code == 0 and res.get("ok"), out[-1200:])
        no_secrets("verify", out)
        check("verify: says the address is the one nginx serves", "the one nginx serves now" in out)
        code, out, res, _ = remote(m, "verify", "--role", "staging", "--sha", "live", "--version", "live")
        check("verify live: ok", code == 0 and res.get("ok") and res.get("version") == "1.16.16", res)
        code, out, res, _ = remote(m, "look")
        check("look after: wired", "the brain IS wired in (1.16.16, XyberRP Staging, host xyberrp.duckdns.org, wrap; "
              "address: the one nginx serves)" in out, [l for l in out.splitlines() if "wired" in l])
        # the brain moved (another secret): verify says so
        conf = open(m.site_real).read()
        open(m.site_real, "w").write(conf.replace(fakes.SECRET, "capri-brain-" + "9" * 48))
        code, out, res, _ = remote(m, "verify", "--role", "staging", "--sha", rep["sha256"], "--version", "1.16.16")
        check("verify: a moved brain is caught", code == 1, out[-600:])
        no_secrets("verify moved", out.replace("capri-brain-" + "9" * 48, ""))
        open(m.site_real, "w").write(conf)
        # the brain does not answer: fetch refuses
        open(os.path.join(m.base, "brain-ok"), "w").write("0")
        code, out, res, _ = remote(m, "fetch", "--role", "staging")
        check("fetch: a silent brain refuses", code == 1 and "does not answer through nginx" in out, out[-400:])
        no_secrets("fetch silent", out)
        open(os.path.join(m.base, "brain-ok"), "w").write("1")

        # the brain's per-address limits
        site_before = open(m.site_real).read()
        code, out, res, _ = remote(m, "guard")
        check("guard: exit 0", code == 0, out[-800:])
        no_secrets("guard", out)
        site = open(m.site_real).read()
        loc = site[site.index(f"location /{fakes.SECRET}/ {{"):]
        loc = loc[:loc.index("}") + 1]
        check("guard: limits inside the brain's location", "limit_req zone=capri_brain burst=12 nodelay;" in loc and
              "limit_conn capri_brain_conn 4;" in loc and "limit_req_status 429;" in loc, loc)
        check("guard: zones at the top", site.startswith("# XyberRP Capri kit: per-address limits for the brain") and
              "limit_req_zone $binary_remote_addr zone=capri_brain:1m rate=12r/m;" in site)
        check("guard: the other location untouched", site.count("limit_req zone=") == 1)
        check("guard: the symlink kept", os.path.islink(m.site))
        rec = json.load(open(os.path.join(m.state, "guard.json")))
        check("guard: backup is the file as it was", open(rec["history"][-1]["backup"]).read() == site_before)
        code, out, res, _ = remote(m, "look")
        check("guard: look sees the limit", "per-address limits: limit_req on, limit_conn on" in out,
              [l for l in out.splitlines() if "limits" in l])
        code, out, res, _ = remote(m, "guard")
        check("guard again: nothing to do (3)", code == 3 and res.get("why") == "already limited", res)
        code, out, res, _ = remote(m, "guard-putback")
        check("guard-putback: exit 0, the file as it was", code == 0 and open(m.site_real).read() == site_before, out[-400:])
        # behind a proxy (only loopback addresses in the log): refused
        log_before = open(m.access_log).read()
        open(m.access_log, "w").write(log_before.replace("203.0.113.7", "127.0.0.1").replace("198.51.100.9", "127.0.0.1"))
        code, out, res, _ = remote(m, "guard")
        check("guard behind a proxy: refused, nothing changed", code == 1 and res.get("why") == "proxied" and
              open(m.site_real).read() == site_before, out[-400:])
        open(m.access_log, "w").write(log_before)
        open(os.path.join(m.base, "nginx-t-fails"), "w").write("1")
        code, out, res, _ = remote(m, "guard")
        check("guard with nginx -t failing: exit 1, put back", code == 1 and open(m.site_real).read() == site_before,
              out[-600:])
        os.remove(os.path.join(m.base, "nginx-t-fails"))

        # put back
        m.set_online("staging", ["3"])
        code, out, res, _ = remote(m, "putback", "--role", "staging")
        check("putback with a player on: exit 3", code == 3 and m.entry("staging")["version"] == "1.16.16")
        m.set_online("staging", [])
        code, out, res, _ = remote(m, "putback", "--role", "staging")
        check("putback: exit 0", code == 0, out[-600:])
        check("putback: the old build named again", m.entry("staging") == old_entry)
        code, out, res, _ = remote(m, "putback", "--role", "staging")
        check("putback twice: nothing to put back (3)", code == 3 and res.get("why") == "nothing recorded", res)
        code, out, res, _ = remote(m, "fetch", "--role", "nowhere")
        check("unknown role: exit 1", code == 1)
    finally:
        m.close()


# ------------------------------------------------------------------------------------------------ the kit's flow
class LocalHost:
    """av_kit.Host's get/put/run over the local files (the machine's side runs here, without SSH)."""

    def __init__(self, machine):
        self.m = machine

    def get(self, remote_path, local):
        shutil.copyfile(remote_path, local)

    def put(self, local, remote_path, mode=0o644):
        shutil.copyfile(local, remote_path)

    def drop(self):
        pass


def install_fake_machine(ck, machine, calls):
    class FakeM:
        def __init__(self, a, log):
            self.log = log
            self.h = LocalHost(machine)
            self.work = None

        def __enter__(self):
            self.work = tempfile.mkdtemp(dir=machine.base)
            return self

        def __exit__(self, *exc):
            shutil.rmtree(self.work, ignore_errors=True)

        def call(self, *args, timeout=600):
            calls.append(args[0])
            code, out, res, _ = remote(machine, args[0], *args[1:], work=self.work)
            for line in out.splitlines():
                if line.startswith("CAPRI "):
                    self.log("  " + line[6:])
            return code, res
    ck.Machine = FakeM


def test_kit_flow():
    import capri_kit as ck
    m = fakes.FakeMachine(ports=(24840, 24778))
    kitdir = tempfile.mkdtemp()
    orig = (ck.HERE, ck.Machine, ck.ask_brain, ck.compile_check)
    try:
        ck.HERE = kitdir
        calls, compiled = [], []
        install_fake_machine(ck, m, calls)
        asked = []
        ck.ask_brain = lambda url, log, chat=True: asked.append(url) or True

        def fake_compile(zip_path, label, a, log, refuse=()):
            data = open(zip_path, "rb").read()
            v = W.wired_values(entries(data)[W.TARGET]) if W.TARGET in entries(data) else {}
            compiled.append((label, v.get("hook")))
            ok = label.endswith("-live") or v.get("hook") not in refuse
            return (0 if ok else 1), {"ok": ok}
        ck.compile_check = fake_compile

        class A:
            role = "staging"; roles = ""; hook = "auto"; force = False; rebuild = False; sha = ""; version = ""
            game = ""; host = "root@example.invalid"; key_from = "xyberrp-staging"
        logs = []
        log = lambda t, quiet=False: logs.append(ck.clean(t))  # noqa: E731

        rc = ck.cmd_publish(A, log)
        check("publish: exit 0", rc == 0, "\n".join(logs[-20:]))
        check("publish: the live package compiled first, then patch", compiled == [("staging-1.16.15-live", None),
                                                                                   ("staging-1.16.16-patch", "patch")], compiled)
        check("publish: brain asked from here with the address", asked == [fakes.URL])
        rec = json.load(open(os.path.join(kitdir, "last-staging.json")))
        check("publish: record", rec["version"] == "1.16.16" and rec["hook"] == "patch" and rec["from"]["version"] == "1.16.15")
        check("publish: the server names it", m.entry("staging")["sha256"] == rec["sha256"])
        check("publish: brain.url not left here", not any(f.endswith(".url") for _, _, fs in os.walk(kitdir) for f in fs))
        check("publish: log has no brain path", not any(fakes.SECRET in l for l in logs))
        m.restart("staging")
        logs.clear()
        rc = ck.cmd_verify(A, log)
        check("verify: exit 0", rc == 0, "\n".join(logs[-20:]))
        logs.clear()
        compiled.clear()
        rc = ck.cmd_publish(A, log)
        check("publish again: already (5), nothing built", rc == ck.ALREADY and compiled == [], (rc, compiled))

        # the compiler refuses the patch: the wrap way
        A.role = "production"
        compiled.clear()
        ck.compile_check = lambda z, l, a, lg: fake_compile(z, l, a, lg, refuse=("patch",))
        rc = ck.cmd_publish(A, log)
        check("publish production, patch refused: wrap", rc == 0 and compiled == [("production-1.16.15-live", None),
              ("production-1.16.16-patch", "patch"), ("production-1.16.16-wrap", "wrap")], (rc, compiled))
        prod = json.load(open(os.path.join(kitdir, "last-production.json")))
        check("publish production: hook wrap, world XyberRP", prod["hook"] == "wrap" and prod["world"] == "XyberRP")
        blob = os.path.join(m.root("production"), ".open77", "mods", prod["sha256"] + ".blob")
        st = entries(open(blob, "rb").read())[W.STORAGE].decode()
        check("publish production: the gate script kept, Capri.Storage.reds untouched", b"mass-override/" in entries(
            open(blob, "rb").read())["r6/scripts/Open77/Open77MassOverride.reds"] and W.PATCH_MARK not in st)
        # both refused: nothing sent
        A.role = "staging"
        A.rebuild = True
        before = m.entry("staging")
        ck.compile_check = lambda z, l, a, lg: fake_compile(z, l, a, lg, refuse=("wrap", "patch"))
        logs.clear()
        try:
            ck.cmd_publish(A, log)
            check("publish, both refused: fails", False)
        except ck.Failed as e:
            check("publish, both refused: fails, nothing sent", "NOTHING was sent" in str(e) and m.entry("staging") == before)
        # the live package does not compile here: nothing judged, nothing sent
        ck.compile_check = lambda z, l, a, lg: (1, {"ok": False})
        try:
            ck.cmd_publish(A, log)
            check("publish, live does not compile: fails", False)
        except ck.Failed as e:
            check("publish, live does not compile: fails", "LIVE package does not compile" in str(e))
        A.rebuild = False
        # players on: early refusal, nothing downloaded or built
        ck.compile_check = fake_compile
        m.set_online("production", ["5"])
        A.role = "production"
        compiled.clear()
        rc = ck.cmd_publish(A, log)
        check("publish with players on: 3, nothing built", rc == 3 and compiled == [], (rc, compiled))
        m.set_online("production", [])
        # put back
        rc = ck.cmd_putback(A, log)
        check("putback production: 0", rc == 0)
        check("putback production: 1.16.15 named again", m.entry("production")["version"] == "1.16.15")
        check("putback: the record moved aside", not os.path.exists(os.path.join(kitdir, "last-production.json")))
    finally:
        ck.HERE, ck.Machine, ck.ask_brain, ck.compile_check = orig
        m.close()
        shutil.rmtree(kitdir, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ the bats
def test_bats():
    bats = os.path.join(KIT, "bats")
    names = sorted(f for f in os.listdir(bats) if f.endswith(".bat.in"))
    check("seven bats", len(names) == 7, names)
    for n in names:
        text = open(os.path.join(bats, n), encoding="ascii").read()
        check(f"{n}: ascii", all(ord(c) < 128 for c in text))
        check(f"{n}: no redirections", "<" not in text and ">" not in text)
        check(f"{n}: no ampersand or pipe", "&" not in text and "|" not in text)
        labels = set(re.findall(r"^:(\w+)", text, re.M))
        for g in re.findall(r"goto (\w+)", text):
            check(f"{n}: goto {g} has its label", g in labels)
        uses_host = "%HOST%" in text
        check(f"{n}: HOST placeholder iff used", ("@@HOST@@" in text) == uses_host)
        bare = re.sub(r"%[A-Za-z_][A-Za-z0-9_]*%", "", text.replace("%~dp0", ""))
        check(f"{n}: no bare percent", "%" not in bare, [l for l in bare.splitlines() if "%" in l][:3])
        for v in re.findall(r"%([A-Z][A-Z0-9_]*)%", text):
            if v in ("LOCALAPPDATA", "USERPROFILE", "ERRORLEVEL"):
                continue
            check(f"{n}: %{v}% is set", re.search(r'set "' + v + "=", text) is not None or v == "HOST")
        if "publish" in text:
            check(f"{n}: restarts with av_kit after publish", "restart --on open77-xbuniverse" in text)
        if "--role production" in text:
            check(f"{n}: production restart says --production", "--production" in text)
    for line in open(os.path.join(bats, "C2-Capri-thinks-with-the-server-on-Staging.bat.in")).read().splitlines():
        check("C2: lines fit", len(line) <= 130, line)


def main():
    for t in (test_build, test_migration, test_refusals, test_remote, test_kit_flow, test_bats):
        try:
            t()
        except Exception:  # noqa: BLE001
            RESULTS.append((t.__name__, False, traceback.format_exc()))
            print(f"FAIL {t.__name__} raised:\n{traceback.format_exc()}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed")
    for name, _, detail in failed:
        print(f"  FAILED: {name}: {str(detail)[:600]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
