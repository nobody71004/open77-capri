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
import time
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
sys.path.insert(0, HERE)
import capri_wire as W
import capri_mo as MO
import capri_voz as Z  # noqa: E402
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


def voice_work(m):
    work = tempfile.mkdtemp(dir=m.base)
    shutil.copy(os.path.join(KIT, "remote", "capri_voice_server.py"), os.path.join(work, "capri_voice_server.py"))
    return work


def test_voice_remote(m):
    """Her voice installed on the machine: venv, the pinned engine, her voice states from the package, the self-test,
    its user and unit, an nginx location of its own with limits; again: nothing to do."""
    code, out, res, work = remote(m, "voice", "--role", "staging")
    check("voice without its server sent: exit 1", code == 1 and "was not sent along" in out, out[-300:])
    code, out, res, work = remote(m, "voice", "--role", "staging", "--check-only", work=voice_work(m))
    check("voice --check-only before: 1, nothing installed", code == 1 and not os.path.exists(m.voice_root + "/venv"),
          out[-400:])
    # a self-test that fails: nothing reaches nginx
    os.makedirs(m.voice_root, exist_ok=True)
    open(os.path.join(m.voice_root, "selftest-fails"), "w").write("1")
    code, out, res, work = remote(m, "voice", "--role", "staging", work=voice_work(m))
    check("voice, self-test fails: exit 1, nginx untouched", code == 1 and "capri-voice-" not in open(m.site_real).read()
          and "the self-test failed" in out and "not her own voice" in out, out[-600:])
    os.remove(os.path.join(m.voice_root, "selftest-fails"))
    site_before = open(m.site_real).read()
    code, out, res, work = remote(m, "voice", "--role", "staging", work=voice_work(m))
    check("voice: exit 0", code == 0 and res.get("changed"), out[-1500:])
    no_secrets("voice", out)
    check("voice: the path never printed", not re.search(r"capri-voice-[0-9a-f]{6,}", out))
    check("voice: her voice states from the package", sorted(os.listdir(os.path.join(m.voice_root, "voces"))) ==
          ["capri_english.safetensors", "capri_spanish.safetensors"])
    pip = open(os.path.join(m.voice_root, "pip-calls")).read()
    check("voice: torch from the CPU index, Pocket TTS pinned", "torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu"
          in pip and "pocket-tts==4.0.1" in pip, pip)
    unit = open(os.path.join(m.unit_dir, "capri-voice.service")).read()
    check("voice: unit runs her server as its own user, offline, read-only but its cache", "User=capri-voice" in unit and
          "HF_HUB_OFFLINE=1" in unit and "ProtectSystem=strict" in unit and f"--port {m.voice_port}" in unit, unit)
    check("voice: its user made", os.path.exists(os.path.join(m.base, "user-made")))
    site = open(m.site_real).read()
    vm = re.search(r"location (/capri-voice-[0-9a-f]{24})/ \{([^}]*)\}", site)
    check("voice: nginx location with its limit, next to the brain's", vm is not None and
          "limit_req zone=capri_voice burst=20 nodelay;" in vm.group(2) and f"proxy_pass http://127.0.0.1:{m.voice_port}/;"
          in vm.group(2) and site.index(vm.group(1)) < site.index(f"location /{fakes.SECRET}/"), site[-900:])
    check("voice: its zone at the top", "limit_req_zone $binary_remote_addr zone=capri_voice:1m rate=40r/m;" in site)
    check("voice: the rest of the site as it was", re.sub(r"(?m)^[ \t]*# XyberRP Capri kit: her voice.*?\n[ \t]*location /capri-voice-[^}]*\}\n",
          "", re.sub(r"^# XyberRP Capri kit: her voice for every player: the limit per address\nlimit_req_zone[^\n]*\n\n", "",
                     site), flags=re.S) == site_before, site[:600])
    rec = json.load(open(os.path.join(m.state, "voice.json")))
    check("voice: record", rec.get("secret", "").startswith("capri-voice-") and rec.get("versions", {}).get("pocket-tts")
          == "4.0.1" and (os.stat(os.path.join(m.state, "voice.json")).st_mode & 0o777) == 0o600, rec)
    check("voice: voice.url 0600", (os.stat(os.path.join(work, "voice.url")).st_mode & 0o777) == 0o600)
    calls = open(os.path.join(m.voice_root, "pip-calls")).read().count("\n")
    code, out, res, work = remote(m, "voice", "--role", "staging", work=voice_work(m))
    check("voice again: nothing to do (3), no pip", code == 3 and res.get("why") == "already" and
          open(os.path.join(m.voice_root, "pip-calls")).read().count("\n") == calls, out[-600:])
    code, out, res, work = remote(m, "voice", "--role", "staging", "--check-only", work=voice_work(m))
    check("voice --check-only after: 3", code == 3, out[-300:])
    code, out, res, _ = remote(m, "look")
    check("look: her voice", "capri-voice: active" in out and "through nginx: answers (en,es" in out,
          [l for l in out.splitlines() if "voice" in l.lower()][:6])


def test_gate_remote(m):
    """Staging's gate replaced by the kit's: kept first, restarted, asked here and through nginx; again: nothing."""
    d = m.gate_dir("staging")
    code, out, res, work = remote(m, "gate", "--role", "staging")
    check("gate without its files sent: exit 1", code == 1 and "were not sent along" in out, out[-300:])
    work = tempfile.mkdtemp(dir=m.base)
    for n in ("gate.js", "dev-server.js"):
        shutil.copy(os.path.join(KIT, "remote", "gate", n), os.path.join(work, n))
    code, out, res, _ = remote(m, "gate", "--role", "staging", work=work)
    check("gate: exit 0", code == 0 and res.get("changed"), out[-800:])
    no_secrets("gate", out)
    check("gate: the kit's files in place", open(os.path.join(d, "dev-server.js")).read() ==
          open(os.path.join(KIT, "remote", "gate", "dev-server.js")).read())
    check("gate: the old ones kept", open(os.path.join(res.get("kept"), "dev-server.js")).read() == "// GET /feed only\n")
    check("gate: production's untouched", open(os.path.join(m.gate_dir("production"), "dev-server.js")).read() ==
          "// GET /feed only\n")
    code, out, res, _ = remote(m, "gate", "--role", "staging", work=work)
    check("gate again: nothing to do (3)", code == 3 and res.get("why") == "already", out[-400:])
    # production's gate, restarted with the new files, does not answer GET /casts: the old ones put back
    open(os.path.join(m.base, "gate-broken"), "w").write("1")
    code, out, res, _ = remote(m, "gate", "--role", "production", work=work)
    check("gate that does not answer after its restart: exit 1, put back", code == 1 and "PUT BACK" in out and
          open(os.path.join(m.gate_dir("production"), "dev-server.js")).read() == "// GET /feed only\n", out[-500:])
    os.remove(os.path.join(m.base, "gate-broken"))
    # a dev-server.js that is not the one handing out casts is refused before anything changes
    open(os.path.join(work, "dev-server.js"), "w").write("// an older gate\n")
    code, out, res, _ = remote(m, "gate", "--role", "production", work=work)
    check("gate: an older dev-server.js refused", code == 1 and "not the one that hands out casts" in out, out[-300:])


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

        # this kit's stopped runs' work folders in the same place are swept (old ones of its own only)
        sweep = os.path.join(m.base, "sweep")
        for n, own, age in (("avkit-old", True, 3 * 3600), ("avkit-young", True, 60), ("avkit-other", False, 3 * 3600)):
            d = os.path.join(sweep, n)
            os.makedirs(d)
            if own:
                open(os.path.join(d, "capri_server.py"), "w").write("#")
            os.utime(d, (time.time() - age, time.time() - age))
        os.makedirs(os.path.join(sweep, "avkit-current"))
        code, out, res, work = remote(m, "fetch", "--role", "staging", work=os.path.join(sweep, "avkit-current"))
        check("fetch: an old work folder of this kit swept, nothing else", sorted(os.listdir(sweep)) ==
              ["avkit-current", "avkit-other", "avkit-young"], os.listdir(sweep))
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

        # what the PC gets: the scripts and every file's hash
        man = json.load(open(os.path.join(work, "manifest.json")))
        sz = entries(open(os.path.join(work, "scripts.zip"), "rb").read())
        check("fetch: scripts.zip holds the scripts and the files a build may edit", sorted(sz) == sorted(
              n for n in entries(live) if n.startswith("r6/scripts/") or n in (Z.PS1, Z.LINUX))
              and all(sz[n] == entries(live)[n] for n in sz), sorted(sz))
        check("fetch: no voice.url before her voice is installed", not os.path.exists(os.path.join(work, "voice.url"))
              and "not on this machine yet" in out and res.get("voice", {}).get("why"), res.get("voice"))
        check("fetch: manifest names the build and hashes every file", man["sha256"] == m.entry("staging")["sha256"] and
              man["entries"] == {n: hashlib.sha256(b).hexdigest() for n, b in entries(live).items()})
        # her voice on the machine, and Staging's gate: what the build names and what verify asks
        test_voice_remote(m)
        test_gate_remote(m)
        code, out, res, work = remote(m, "fetch", "--role", "staging")
        check("fetch with her voice: voice.url 0600", (os.stat(os.path.join(work, "voice.url")).st_mode & 0o777) == 0o600
              and res.get("voice", {}).get("languages") == "en,es", res.get("voice"))
        voice_url = open(os.path.join(work, "voice.url")).read().strip()
        check("fetch with her voice: the voice's address", re.match(r"^https://xyberrp\.duckdns\.org/capri-voice-[0-9a-f]{24}/v1$",
              voice_url) is not None)
        no_secrets("fetch with her voice", out.replace(voice_url, ""))
        check("fetch: her voice's path not printed", voice_url.split("/")[3] not in out)
        # assemble: the package made on the machine from the live one and the changed scripts
        sdata, srep = W.build(W.write_zip(sz), url, fakes.HOST, "XyberRP Staging", "1.16.16", "patch",
                              extras={"files": MO.render("staging", "1.16.16"),
                                      "voice": {"url": voice_url, "langs": Z.languages(man["entries"])}})
        check("build: the changed files", sorted(srep["changed"]) == sorted([W.TARGET, W.STORAGE, MO.O77, MO.CAPRI,
              Z.PS1, Z.LINUX, Z.SERVIDOR]), srep["changed"])
        built = entries(sdata)
        delta = {n: built[n] for n in srep["changed"]}
        expect = dict(man["entries"])
        expect.update({n: hashlib.sha256(b).hexdigest() for n, b in delta.items()})
        open(os.path.join(work, "changes.zip"), "wb").write(W.write_zip(delta))
        json.dump(expect, open(os.path.join(work, "expect.json"), "w"))
        code, out, res, _ = remote(m, "assemble", "--role", "staging", "--delta", os.path.join(work, "changes.zip"),
                                   "--expect", os.path.join(work, "expect.json"), "--expect-sha", man["sha256"], work=work)
        check("assemble: exit 0", code == 0, out[-600:])
        asm = entries(open(os.path.join(work, "assembled.zip"), "rb").read())
        check("assemble: every file as built", {n: hashlib.sha256(b).hexdigest() for n, b in asm.items()} == expect)
        check("assemble: the archive and the DLL from the live package", asm["archive/pc/mod/CapriPersonalityConstruct.archive"]
              == entries(live)["archive/pc/mod/CapriPersonalityConstruct.archive"])
        check("assemble: result names its sha", res.get("sha256") == hashlib.sha256(open(os.path.join(work, "assembled.zip"),
              "rb").read()).hexdigest())
        bad = dict(expect)
        bad[W.TARGET] = "0" * 64
        json.dump(bad, open(os.path.join(work, "expect-bad.json"), "w"))
        code, out, res, _ = remote(m, "assemble", "--role", "staging", "--delta", os.path.join(work, "changes.zip"),
                                   "--expect", os.path.join(work, "expect-bad.json"), "--expect-sha", man["sha256"], work=work)
        check("assemble: a hash that differs is refused", code == 1 and "not the one the PC built" in out, out[-300:])
        open(os.path.join(work, "evil.zip"), "wb").write(W.write_zip({"red4ext/plugins/X/x.dll": b"MZ"}))
        code, out, res, _ = remote(m, "assemble", "--role", "staging", "--delta", os.path.join(work, "evil.zip"),
                                   "--expect", os.path.join(work, "expect.json"), "--expect-sha", man["sha256"], work=work)
        check("assemble: a change that is not a Capri script is refused", code == 1 and "a build may not change" in out,
              out[-300:])
        code, out, res, _ = remote(m, "assemble", "--role", "staging", "--delta", os.path.join(work, "changes.zip"),
                                   "--expect", os.path.join(work, "expect.json"), "--expect-sha", "e" * 64, work=work)
        check("assemble: another live package is refused", code == 1 and "not the one the build was made from" in out)
        new = open(os.path.join(work, "assembled.zip"), "rb").read()
        rep = {"sha256": hashlib.sha256(new).hexdigest()}
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
        check("verify after the restart: ok", code == 0 and res.get("ok"), out[-1600:])
        no_secrets("verify", out.replace(voice_url, ""))
        check("verify: her voice named and answering", "its servidor.json names her voice as nginx serves it now" in out
              and "Capri Voz carries the server voice" in out, [l for l in out.splitlines() if "voice" in l])
        check("verify: Mass Override for everyone, the gate answers", "every player runs every cast" in out and
              "mass-override-staging" in out, [l for l in out.splitlines() if "Mass Override" in l])
        check("verify: voice.url for the PC", open(os.path.join(_, "voice.url")).read().strip() == voice_url
              if os.path.exists(os.path.join(_, "voice.url")) else False)
        check("verify: says the address is the one nginx serves", "the one nginx serves now" in out)
        code, out, res, _ = remote(m, "verify", "--role", "staging", "--sha", "live", "--version", "live")
        check("verify live: ok", code == 0 and res.get("ok") and res.get("version") == "1.16.16", res)
        code, out, res, _ = remote(m, "look")
        check("look after: wired", "the brain IS wired in (1.16.16, XyberRP Staging, host xyberrp.duckdns.org, patch; "
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
        check("guard: the other locations untouched", site.count("limit_req zone=capri_brain") == 1 and
              "location /mass-override-staging/ { proxy_pass http://127.0.0.1:11900/; proxy_read_timeout 15s; "
              "proxy_buffering off; }" in site)
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
        def __init__(self, a, log, extra=()):
            self.log = log
            self.h = LocalHost(machine)
            self.work = None
            self.extra = [p for k in extra for p in ck.EXTRAS[k]]

        def __enter__(self):
            self.work = tempfile.mkdtemp(dir=machine.base)
            for p in self.extra:
                shutil.copy(p, os.path.join(self.work, os.path.basename(p)))
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
    orig = (ck.HERE, ck.Machine, ck.ask_brain, ck.compile_check, ck.ask_voice, ck.ask_gate, ck.check_capri_voz)
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

        voiced, gated, vozchecked = [], [], []
        # the stand-in Capri Voz files are only the places the edits go (no program): their check is the build's own
        ck.check_capri_voz = lambda ents, log: vozchecked.append(sorted(n for n in ents if "CapriVoz" in n)) or True
        ck.ask_voice = lambda url, log: voiced.append(url) or True
        ck.ask_gate = lambda base, log: gated.append(base) or True
        try:
            ck.cmd_publish(A, log)
            check("publish before her voice is installed: refused", False)
        except ck.Failed as e:
            check("publish before her voice is installed: refused", "her voice is not on the machine yet" in str(e))
        rc = ck.cmd_voice(A, log)
        check("kit voice: exit 0, asked from here", rc == 0 and len(voiced) == 1 and "/capri-voice-" in voiced[0],
              "\n".join(logs[-12:]))
        rc = ck.cmd_gate(A, log)
        check("kit gate: exit 0, asked from here", rc == 0 and gated == ["https://xyberrp.duckdns.org/mass-override-staging"],
              (rc, gated, logs[-6:]))
        check("kit: no voice path in the log", not any(re.search(r"capri-voice-[0-9a-f]{6,}", l) for l in logs))
        rc = ck.cmd_publish(A, log)
        check("publish: exit 0", rc == 0, "\n".join(logs[-20:]))
        check("publish: Capri Voz checked before anything was sent", vozchecked and Z.PS1 in vozchecked[0] and
              Z.LINUX in vozchecked[0], vozchecked)
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
        prod_entries = entries(open(blob, "rb").read())
        check("publish production: its own gate in Mass Override, Capri.Storage.reds untouched (wrap)",
              MO.values(prod_entries[MO.O77]) == {"base": "https://xyberrp.duckdns.org/mass-override", "label": "production",
                                                    "build": "1.16.16", "everyone": True} and W.PATCH_MARK not in st,
              MO.values(prod_entries[MO.O77]))
        sv = Z.servidor_values(prod_entries[Z.SERVIDOR])
        check("publish production: servidor.json names her voice and XyberRP", sv.get("mundo") == "XyberRP" and
              sv.get("url") == voiced[0] and sv.get("idiomas") == "en,es", sv)
        check("publish production: Capri Voz edited, her voice states untouched", Z.MARK.encode() in prod_entries[Z.PS1]
              and prod_entries[Z.VOICES_DIR + "/capri_english.safetensors"] == b"EN" * 300)
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
        ck.HERE, ck.Machine, ck.ask_brain, ck.compile_check, ck.ask_voice, ck.ask_gate, ck.check_capri_voz = orig
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
    for line in open(os.path.join(bats, "C2-Capri-brain-voice-and-Mass-Override-on-Staging.bat.in")).read().splitlines():
        check("C2: lines fit", len(line) <= 130, line)
    for n in ("C2-Capri-brain-voice-and-Mass-Override-on-Staging.bat.in", "C3-Capri-brain-voice-and-Mass-Override-on-XyberRP.bat.in"):
        text = open(os.path.join(bats, n)).read()
        order = [text.index(x) for x in (" voice --role ", " gate --role ", " publish --role ", " restart --on ", " verify --role ")]
        check(f"{n}: voice, gate, publish, restart, verify in that order", order == sorted(order), order)
        role = "staging" if "Staging" in n else "production"
        check(f"{n}: every step on {role}", text.count(f"--role {role}") == 4 and
              text.count("--role staging" if role == "production" else "--role production") == 0)


def test_one_line_site():
    """XyberRP's own site file writes its locations on one line each ("location /x/ { proxy_pass ...; }"): the brain's
    limits go into that line (2026-11-12: the first guard found the brain's location "0 times" there), and her voice's
    location goes in above it."""
    m = fakes.FakeMachine(ports=(26840, 26778))
    try:
        site = open(m.site_real).read()
        multi = f"    location /{fakes.SECRET}/ {{\n        proxy_pass http://127.0.0.1:8890/;\n        proxy_read_timeout 300s;\n    }}\n"
        check("one-line: the fake site has the brain's block", multi in site)
        one = f"    location /{fakes.SECRET}/ {{ proxy_pass http://127.0.0.1:8890/; proxy_read_timeout 300s; }}\n"
        open(m.site_real, "w").write(site.replace(multi, one))
        before = open(m.site_real).read()
        code, out, res, _ = remote(m, "guard")
        check("one-line guard: exit 0", code == 0, out[-800:])
        after = open(m.site_real).read()
        check("one-line guard: the limits inside the brain's line, the mark above it",
              f"    # XyberRP Capri kit: per-address limits (in the location below)\n    location /{fakes.SECRET}/ {{ "
              "limit_req zone=capri_brain burst=12 nodelay; limit_req_status 429; limit_conn capri_brain_conn 4; "
              "limit_conn_status 429; proxy_pass http://127.0.0.1:8890/; proxy_read_timeout 300s; }" in after, after[-700:])
        code, out, res, _ = remote(m, "look")
        check("one-line guard: nginx -T reads the limit in", "per-address limits: limit_req on, limit_conn on" in out,
              [l for l in out.splitlines() if "limits" in l])
        code, out, res, _ = remote(m, "guard-putback")
        check("one-line guard-putback: as it was", code == 0 and open(m.site_real).read() == before)
        # this machine refuses the unit's sandbox (an unprivileged container): the unit again without it
        open(os.path.join(m.base, "no-namespaces"), "w").write("1")
        code, out, res, work = remote(m, "voice", "--role", "production", work=voice_work(m))
        check("one-line voice: exit 0", code == 0, out[-800:])
        unit = open(os.path.join(m.unit_dir, "capri-voice.service")).read()
        check("voice in a container refusing namespaces: the unit without its sandbox, still its own user",
              "once more without them" in out and "ProtectSystem" not in unit and "User=capri-voice" in unit, out[-900:])
        code, out, res, work = remote(m, "voice", "--role", "production", work=voice_work(m))
        check("voice again there: nothing to do (3)", code == 3, out[-500:])
        after = open(m.site_real).read()
        check("one-line voice: its location above the brain's line", re.search(
              r"    location /capri-voice-[0-9a-f]{24}/ \{\n(        [^\n]*\n)+    \}\n    location /" + fakes.SECRET, after)
              is not None, after[-900:])
    finally:
        m.close()


def test_voz():
    """capri_voz on the stand-ins (and on Capri's real files when CAPRI_VOZ_REAL names a folder holding them)."""
    for name, fixture, patch in (("ps1", fakes.PS1_FIXTURE, Z.patch_ps1), ("linux", fakes.LINUX_FIXTURE, Z.patch_linux)):
        out, had = patch(fixture)
        check(f"voz {name}: edited, not before", not had and Z.MARK.encode() in out)
        again, had2 = patch(out)
        check(f"voz {name}: editing the edited file gives the same bytes", again == out and had2)
        check(f"voz {name}: Capri's own back", Z.original(out, name) == fixture)
        broken = fixture.replace(b"$Version = 17", b"$Version = 16") if name == "ps1" else fixture.replace(b"VERSION = 17", b"VERSION = 16")
        try:
            patch(broken)
            check(f"voz {name}: a changed anchor refuses", False)
        except Z.VozError as e:
            check(f"voz {name}: a changed anchor refuses", "'version'" in str(e), str(e))
    check("voz ps1: the BOM kept", Z.patch_ps1(fakes.PS1_FIXTURE)[0].startswith(b"\xef\xbb\xbf"))
    crlf = fakes.PS1_FIXTURE.replace(b"\n", b"\r\n")
    out, _ = Z.patch_ps1(crlf)
    check("voz ps1: CRLF kept", b"\n" not in out.replace(b"\r\n", b"") and Z.original(out, "ps1") == crlf)
    sj = Z.servidor_json("https://xyberrp.duckdns.org/capri-voice-" + "a" * 24 + "/v1", "XyberRP", "1.16.17", "en,es")
    check("voz servidor.json", Z.servidor_values(sj) == {**Z.servidor_values(sj), "url": "https://xyberrp.duckdns.org/capri-voice-"
          + "a" * 24 + "/v1", "mundo": "XyberRP", "paquete": "1.16.17", "idiomas": "en,es", "voz": "capri"})
    try:
        Z.servidor_json("http://evil.example/v1", "XyberRP", "1.16.17", "en")
        check("voz servidor.json refuses a plain address", False)
    except Z.VozError:
        check("voz servidor.json refuses a plain address", True)
    check("voz languages", Z.languages({Z.VOICES_DIR + "/capri_english.safetensors": 1, Z.VOICES_DIR + "/capri_spanish.safetensors": 1,
                                        Z.VOICES_DIR + "/capri.wav": 1}) == "en,es")
    real = os.environ.get("CAPRI_VOZ_REAL", "")
    if real and os.path.isfile(os.path.join(real, "CapriVoz.ps1")):
        ps1 = open(os.path.join(real, "CapriVoz.ps1"), "rb").read()
        lin = open(os.path.join(real, "capri_voz_linux.py"), "rb").read()
        p1, _ = Z.patch_ps1(ps1)
        p2, _ = Z.patch_linux(lin)
        check("voz real: both edited and back", Z.original(p1, "ps1") == ps1 and Z.original(p2, "linux") == lin)
        try:
            compile(p2.decode("utf-8"), "capri_voz_linux.py", "exec")
            check("voz real: the Linux one compiles", True)
        except SyntaxError as e:
            check("voz real: the Linux one compiles", False, str(e))
        check("voz real: no character outside ASCII added to the PowerShell one",
              not (set(p1.decode("utf-8")) - set(ps1.decode("utf-8"))) - set(map(chr, range(128))))
    else:
        print("(CAPRI_VOZ_REAL not set: Capri's real Capri Voz files not tested here)")


def test_mo():
    for role, base in (("staging", "https://xyberrp.duckdns.org/mass-override-staging"),
                       ("production", "https://xyberrp.duckdns.org/mass-override")):
        f = MO.render(role, "1.16.17")
        check(f"mo {role}: its gate, label and build", MO.values(f[MO.O77]) == {"base": base, "label": role,
              "build": "1.16.17", "everyone": True}, MO.values(f[MO.O77]))
    repo = os.path.dirname(KIT)
    for path, tpl in MO.TEMPLATES.items():
        game = os.path.join(repo, "game", path)
        if os.path.isfile(game):
            check(f"mo: the kit's {os.path.basename(path)} is the repo's", open(game, "rb").read() == open(tpl, "rb").read())
    for n in ("gate.js", "dev-server.js"):
        src = os.path.join(repo, "mass-override", n)
        if os.path.isfile(src):
            check(f"gate: the kit's {n} is the repo's", open(src, "rb").read() ==
                  open(os.path.join(KIT, "remote", "gate", n), "rb").read())


def main():
    for t in (test_build, test_migration, test_refusals, test_voz, test_mo, test_remote, test_one_line_site,
              test_kit_flow, test_bats):
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
