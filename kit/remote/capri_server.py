#!/usr/bin/env python3
"""XyberRP's Capri on the game servers' machine: what the kit on the owner's PC (capri_kit.py) asks of it.

    capri_server.py look    WORK [--roles staging,production]       READ ONLY: both servers' Capri package (is the
                            brain wired in?), the players on, the brain (nginx, its unit, Ollama, what it answers,
                            what it was asked lately)
    capri_server.py fetch   WORK --role ROLE                        READ ONLY: the package ROLE hands out now, into
                            WORK/capri-current.zip, its scripts into WORK/scripts.zip and every file's hash into
                            WORK/manifest.json (what the PC needs: a few hundred KB), and the brain's address as nginx
                            serves it into WORK/brain.url (0600; the kit reads it, nobody prints it)
    capri_server.py assemble WORK --role ROLE --delta DELTA.zip --expect EXPECT.json --expect-sha SHA
                            the new package made here from the live one (fetch copied it) and the PC's changed
                            scripts; every file must hash to what the PC built and compiled (WORK/assembled.zip)
    capri_server.py import  WORK --role ROLE --zip ZIP --version V --expect-sha SHA [--force]
                            ZIP into ROLE's hosted mod store and ROLE's capri-personality-construct entry pointed at it
                            (only its version, sha256 and sizeBytes change) -- refused when the entry is no longer SHA
                            (somebody published since), or with players on (unless --force); server.jsonc kept first,
                            the server's own --check-config run (put back by itself if it fails).  Restart afterwards.
    capri_server.py verify  WORK --role ROLE --sha SHA --version V  READ ONLY, after the restart: the manifest players
                            get names SHA and V, the blob it serves hashes to SHA, the script in it carries the address
                            nginx serves now, and the server said "Required mods" at its start
    capri_server.py putback WORK --role ROLE [--force]              the entry back to what the last import replaced
    capri_server.py guard   WORK                                    per-address limits on the brain's nginx location
                            (limit_req/limit_conn, 429): kept first, nginx -t, reload, the brain asked again through
                            nginx -- put back by itself if anything is wrong; nothing when a limit is there already
    capri_server.py guard-putback WORK                              the site file as it was before the limits
    capri_server.py voice   WORK [--role ROLE] [--check-only]       Capri's own voice for every player, on this machine
                            (Pocket TTS 4.0.1 + torch 2.15.0 CPU in /opt/capri-voice, her voice states from ROLE's
                            live Capri package, a self-test in each language, the capri-voice unit on 127.0.0.1:8891,
                            and an nginx location with its own private path and per-address limits next to the
                            brain's) -- every step checked, nginx put back by itself on any failure; nothing done
                            when it is all there and answering already.  WORK/voice.url (0600) for the kit.
    capri_server.py gate    WORK --role ROLE                        ROLE's Mass Override gate (the open77-mass-override
                            units) updated to WORK/gate.js + WORK/dev-server.js: kept first, restarted, asked
                            locally and through nginx -- put back by itself on any failure

ROLE: staging (/opt/open77-xbuniverse-staging, "XyberRP Staging") or production (/opt/open77-xbuniverse, "XyberRP");
SERVERS_ROOT moves /opt.  Every line it prints starts "CAPRI "; the outcome is one "CAPRI-RESULT {json}" line.
The brain's path is a secret: it is never printed (capri-brain-<secret>), nor any address but loopback, nor any
key.  Exit 0 done, 3 nothing changed (players on, or nothing to do), 1 something failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
try:
    import fcntl
except ImportError:  # Windows: the kit's rehearsal runs this file's code there; the lock is the machine's (Linux)
    fcntl = None
import urllib.error
import urllib.request
import zipfile

MOD_ID = "capri-personality-construct"
TARGET = "r6/scripts/CapriPersonalityConstruct/Capri.ServerBrain.reds"
ROLES = {"staging": ("open77-xbuniverse-staging", "XyberRP Staging"), "production": ("open77-xbuniverse", "XyberRP")}
SERVERS_ROOT = os.environ.get("SERVERS_ROOT", "/opt")
SYSTEMCTL = os.environ.get("SYSTEMCTL", "systemctl").split()
STATE_DIR = os.environ.get("CAPRI_KIT_STATE", "/root/capri-kit")
NGINX = os.environ.get("CAPRI_NGINX", "nginx").split()
CURL = os.environ.get("CAPRI_CURL", "curl").split()
SECRET_RX = re.compile(r"capri-brain-[0-9A-Za-z]{6,}")
VOICE_SECRET_RX = re.compile(r"capri-voice-[0-9a-fA-F]{12,}")   # its path: capri-voice-<24 hex>
# Capri's voice on this machine (cmd_voice)
VOICE_ROOT = os.environ.get("CAPRI_VOICE_ROOT", "/opt/capri-voice")
VOICE_PORT = int(os.environ.get("CAPRI_VOICE_PORT", "8891"))
VOICE_UNIT = os.environ.get("CAPRI_VOICE_UNIT", "capri-voice")
VOICE_UNIT_DIR = os.environ.get("CAPRI_VOICE_UNIT_DIR", "/etc/systemd/system")
VOICE_USER = os.environ.get("CAPRI_VOICE_USER", "capri-voice")
VOICE_PYTHON = os.environ.get("CAPRI_VOICE_PYTHON", "")      # the Python to make its venv with (else the system's)
POCKET_PIN = "4.0.1"        # what a player's own local engine runs (checked on the owner's laptop, 2026-11-12)
TORCH_PIN = "2.15.0"
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
STANDALONE_URL = os.environ.get("CAPRI_STANDALONE_URL") or (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20261026/"
    "cpython-3.11.18%2B20261026-x86_64-unknown-linux-gnu-install_only.tar.gz")
STANDALONE_SHA = os.environ.get("CAPRI_STANDALONE_SHA") or \
    "a87ee63646c8f8438b7af3954b2135ed2af91d033c631f12a8f20af903046d06"   # 49036443 B (checked 2026-11-12)
STANDALONE_VERSION = "3.11.18"
VOICE_RATE = "40r/m"        # one address: twenty lines at once, then one every second and a half
VOICE_BURST = 20
VOICE_MARK = "# XyberRP Capri kit: her voice for every player"
VOICE_FILES = "red4ext/plugins/CapriPersonalityConstruct/CapriVoz/voces/"
CAPRIVOZ = "red4ext/plugins/CapriPersonalityConstruct/CapriVoz/"
# the Mass Override gates (cmd_gate): folder under SERVERS_ROOT, unit, local port, public path
GATES = {"staging": ("open77-mass-override-staging", "open77-mass-override-staging",
                     int(os.environ.get("CAPRI_GATE_PORT_STAGING", "11900")), "/mass-override-staging/"),
         "production": ("open77-mass-override", "open77-mass-override",
                        int(os.environ.get("CAPRI_GATE_PORT_PRODUCTION", "11901")), "/mass-override/")}
IPV4_RX = re.compile(r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
KEYISH_RX = re.compile(r"(?i)key|token|secret|pass|cred|auth")
NO = 3


class Failed(Exception):
    pass


def clean(text) -> str:
    text = SECRET_RX.sub("capri-brain-<secret>", str(text))
    text = VOICE_SECRET_RX.sub("capri-voice-<secret>", text)
    return IPV4_RX.sub("<addr>", text)


def say(text=""):
    for line in str(text).splitlines() or [""]:
        print("CAPRI " + clean(line), flush=True)


def result(**kw):
    print("CAPRI-RESULT " + clean(json.dumps(kw, sort_keys=True)), flush=True)


def where(e) -> str:
    """Where an unexpected error came from: file names, lines and functions only (never a value)."""
    frames = traceback.extract_tb(e.__traceback__)[-6:]
    return " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in reversed(frames))


# The commands that change this machine, and how long one waits (s) for another run of this kit that is changing it:
# two bats run at once (C2 and C3) take turns instead of working on the same files at the same moment.  Under the
# caller's own timeout (capri_kit.py: 3600 s for voice, 600 s for the others).
CHANGING = {"voice": 3000, "gate": 480, "assemble": 480, "import": 480, "putback": 480, "guard": 480,
            "guard-putback": 480, "brain": 480}


class MachineLock:
    """STATE_DIR/kit.lock (flock), held while one command changes this machine; it names its holder.  The kernel lets
    go of it when the holder ends, however it ends (a dropped SSH session too): nothing is ever left locked."""

    def __init__(self, a):
        self.a = a
        wait = os.environ.get("CAPRI_KIT_LOCK_WAIT", "")
        self.limit = int(wait) if wait.isdigit() else CHANGING[a.command]
        self.path = os.path.join(STATE_DIR, "kit.lock")
        self.f = None

    def holder(self) -> str:
        try:
            with open(self.path, encoding="utf-8") as f:
                h = json.loads(f.read() or "{}")
        except (OSError, ValueError):
            h = {}
        if not h:
            return "another run of this kit"
        what = h.get("command", "?") + (f" for {h['role']}" if h.get("role") else "")
        return f"{what}, pid {h.get('pid', '?')}, since {h.get('since', '?')} UTC"

    def __enter__(self):
        if fcntl is None:
            return self
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        self.f = open(self.path, "a+", encoding="utf-8")
        t0 = time.time()
        told = 0.0
        while True:
            try:
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                now = time.time()
                if now - t0 >= self.limit:
                    who = self.holder()
                    self.f.close()
                    raise Failed(f"another run of this kit is still changing this machine ({who}) after "
                                 f"{int(now - t0)} s of waiting: nothing done here -- run this again when it is done")
                if now - told >= 30:
                    say(f"another run of this kit is changing this machine ({self.holder()}): waiting for it "
                        f"({int(now - t0)} s so far, {max(1, self.limit // 60)} min at most)")
                    told = now
                time.sleep(1)
        waited = time.time() - t0
        if waited >= 1:
            say(f"the other run is done (waited {waited:.0f} s): this one goes on")
        self.f.seek(0)
        self.f.truncate()
        self.f.write(json.dumps({"pid": os.getpid(), "command": self.a.command, "role": self.a.role or "",
                                 "since": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}))
        self.f.flush()
        return self

    def __exit__(self, *exc):
        if self.f is None:
            return
        try:
            self.f.seek(0)
            self.f.truncate()
            self.f.flush()
        finally:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            self.f.close()


def run(argv, timeout=60, env=None, cwd=None):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, f"{e.__class__.__name__}: {e}"


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ server.jsonc
def strip_jsonc(value: str) -> str:
    out, i, n, quoted = [], 0, len(value), False
    while i < n:
        c = value[i]
        if quoted:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(value[i + 1])
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            out.append(c)
        elif value.startswith("//", i):
            while i < n and value[i] != "\n":
                i += 1
            continue
        elif value.startswith("/*", i):
            j = value.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def object_spans(text: str) -> list[tuple[int, int]]:
    """Every {...} of a JSONC text as (start, end+1), strings and comments skipped."""
    spans, stack, i, n, quoted = [], [], 0, len(text), False
    while i < n:
        c = text[i]
        if quoted:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        elif c == "{":
            stack.append(i)
        elif c == "}" and stack:
            spans.append((stack.pop(), i + 1))
        i += 1
    return spans


def entry_span(text: str) -> tuple[int, int]:
    hits = [m.start() for m in re.finditer(r'"id"\s*:\s*"' + re.escape(MOD_ID) + '"', text)]
    if len(hits) != 1:
        raise Failed(f"server.jsonc names {MOD_ID} {len(hits)} times (one expected)")
    inner = [s for s in object_spans(text) if s[0] < hits[0] < s[1]]
    if not inner:
        raise Failed(f"{MOD_ID} is not inside an object in server.jsonc")
    return min(inner, key=lambda s: s[1] - s[0])


def packages(cfg: dict) -> list:
    rm = cfg.get("requiredMods") or {}
    for key in ("packages", "mods", "required", "list", "items"):
        if isinstance(rm, dict) and isinstance(rm.get(key), list):
            return rm[key]
    return rm if isinstance(rm, list) else []


def capri_entry(cfg: dict) -> dict | None:
    return next((p for p in packages(cfg) if isinstance(p, dict) and p.get("id") == MOD_ID), None)


def role_paths(role: str):
    if role not in ROLES:
        raise Failed(f"no such role {role!r} (staging or production)")
    name, world = ROLES[role]
    root = os.path.join(SERVERS_ROOT, name)
    if not os.path.isfile(os.path.join(root, "server.jsonc")):
        raise Failed(f"{root}/server.jsonc is not there")
    return name, world, root


def load_cfg(root: str) -> tuple[str, dict]:
    text = open(os.path.join(root, "server.jsonc"), encoding="utf-8").read()
    return text, json.loads(strip_jsonc(text))


def mods_dir(root: str, cfg: dict) -> str:
    # the hosted store: .open77/mods next to server.jsonc (the publisher and the launcher's server side)
    return os.path.join(root, ".open77", "mods")


# ------------------------------------------------------------------------------------------------ the server
def online(root: str) -> list[str]:
    """Connections opened and not closed since the last start (server.log)."""
    path = os.path.join(root, "server.log")
    if not os.path.isfile(path):
        return []
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    start = max([i for i, l in enumerate(lines) if "Server configuration:" in l] or [0])
    live = {}
    for l in lines[start:]:
        m = re.search(r"Connection (\d+) (opened|closed)", l)
        if m:
            live[m.group(1)] = m.group(2) == "opened"
    return [k for k, v in live.items() if v]


def last_start_lines(root: str, rx: str, n: int = 6) -> list[str]:
    path = os.path.join(root, "server.log")
    if not os.path.isfile(path):
        return []
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    start = max([i for i, l in enumerate(lines) if "Server configuration:" in l] or [0])
    return [l for l in lines[start:] if re.search(rx, l)][-n:]


def unit_state(unit: str) -> str:
    code, out = run(SYSTEMCTL + ["is-active", unit], timeout=20)
    return out.strip().splitlines()[-1] if out.strip() else "?"


def open77_version(root: str) -> str:
    try:
        return json.load(open(os.path.join(root, "package-manifest.json"))).get("version") or "?"
    except (OSError, ValueError):
        return "?"


def check_config(unit: str, root: str) -> tuple[int, str]:
    """--check-config exactly as the unit starts the server (its command line, folder and environment; nothing of
    that environment printed)."""
    def show(prop):
        code, out = run(SYSTEMCTL + ["show", "-p", prop, "--value", unit], timeout=20)
        return out.strip() if code == 0 else ""
    env = dict(os.environ)
    for f in re.findall(r"(/[^\s()]+)", show("EnvironmentFiles")):
        try:
            for line in open(f, encoding="utf-8", errors="replace"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                env[k.strip()] = v
        except OSError:
            pass
    try:
        for item in shlex.split(show("Environment")):
            if "=" in item:
                k, v = item.split("=", 1)
                env[k] = v
    except ValueError:
        pass
    m = re.search(r"argv\[\]=([^;]+);", show("ExecStart"))
    argv = shlex.split(m.group(1)) if m else []
    wd = show("WorkingDirectory") or root
    if not argv or not any("Open77.Server" in a for a in argv):
        argv, wd = ["./Open77.Server", "--config", "server.jsonc"], root
    first = next((i for i, a in enumerate(argv) if os.path.basename(a) in ("dotnet", "dotnet.exe")
                  or os.path.basename(a).startswith("Open77.Server")), 0)
    argv = [a for a in argv[first:] if a != "--no-setup"] + ["--no-setup", "--check-config"]
    if "--config" not in argv and not any(a.startswith("--config=") for a in argv):
        argv += ["--config", "server.jsonc"]
    code, out = run(argv, timeout=120, env=env, cwd=wd)
    return code, "\n".join(out.strip().splitlines()[-6:])


def http_json(url: str, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def manifest(cfg: dict, want_sha: str | None = None):
    """(port, manifest) of the server's own mod manifest: game port + 1 first, then the ports around it -- the one
    that lists Capri (with want_sha, the one whose Capri is that build: other servers share the host)."""
    try:
        base = int((cfg.get("network") or {}).get("port"))
    except (TypeError, ValueError):
        return None, None
    seen = None
    for port in [base + 1] + [p for p in range(base - 12, base + 13) if p != base + 1]:
        try:
            body = http_json(f"http://127.0.0.1:{port}/mods/v1/manifest", timeout=2)
        except Exception:  # noqa: BLE001 -- nothing there, or not a manifest
            continue
        mods = body.get("mods") or body.get("packages") or []
        hit = next((m for m in mods if isinstance(m, dict) and m.get("id") == MOD_ID), None)
        if hit is None:
            continue
        if want_sha is None or hit.get("sha256") == want_sha:
            return port, body
        seen = seen or (port, body)
    return seen if want_sha is None else (None, None)


def query_status(port):
    try:
        body = http_json(f"http://127.0.0.1:{port}/query/v1/status", timeout=3)
        return body.get("numplayers"), body.get("status")
    except Exception:  # noqa: BLE001
        return None, None


# ------------------------------------------------------------------------------------------------ packages
def zip_look(path_or_bytes) -> dict:
    """What a Capri package holds: files, and what its Capri.ServerBrain.reds (if any) says."""
    data = open(path_or_bytes, "rb").read() if isinstance(path_or_bytes, str) else path_or_bytes
    out = {"files": 0, "wired": False}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")]
        out["files"] = len(names)
        if CAPRIVOZ + "servidor.json" in names:
            try:
                sv = json.loads(z.read(CAPRIVOZ + "servidor.json").decode("utf-8"))
                out["voice_url"] = sv.get("url")
                out["voice_world"] = sv.get("mundo")
            except (ValueError, UnicodeDecodeError):
                out["voice_url"] = "unreadable"
        if CAPRIVOZ + "CapriVoz.ps1" in names:
            out["voz_patched"] = b"XyberRP server voice" in z.read(CAPRIVOZ + "CapriVoz.ps1")
        mo = "r6/scripts/Open77/Open77MassOverride.reds"
        if mo in names:
            mtext = z.read(mo).decode("utf-8", errors="replace")
            for key, rx in (("mo_base", r'func Base\(\) -> String \{ return "([^"]*)"; \}'),
                            ("mo_label", r'func Label\(\) -> String \{ return "([^"]*)"; \}'),
                            ("mo_build", r'func Version\(\) -> String \{ return "([^"]*)"; \}')):
                hit = re.search(rx, mtext)
                out[key] = hit.group(1) if hit else None
            out["mo_everyone"] = "class MassOverrideRemote" in mtext
        if TARGET in names:
            text = z.read(TARGET).decode("utf-8", errors="replace")
            out["wired"] = True
            for key in ("Package", "World", "Url", "Host", "Model"):
                m = re.search(r"public static func " + key + r"\(\) -> String \{ return \"([^\"]*)\"; \}", text)
                out[key.lower()] = m.group(1) if m else None
            out["hook"] = "wrap" if "@wrapMethod(CapriStorage)" in text else "patch"
    return out


# ------------------------------------------------------------------------------------------------ the brain
def nginx_sites() -> list[dict]:
    """nginx -T read into server blocks: names, listens, and their locations (path, proxy_pass, limit_req)."""
    code, out = run(NGINX + ["-T"], timeout=30)
    if code != 0 and "server {" not in out and "server{" not in out:
        raise Failed(f"nginx -T did not answer: {out.strip().splitlines()[-1:] if out.strip() else code}")
    sites, depth, cur, loc, loc_depth, conf = [], 0, None, None, None, None
    for raw in out.splitlines():
        mf = re.match(r"^# configuration file (.+):\s*$", raw.strip())
        if mf:
            conf = mf.group(1)
            continue
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if cur is None and re.match(r"^server\s*\{", line):
            cur = {"names": [], "listens": [], "locations": [], "file": conf}
            sites.append(cur)
            depth = line.count("{") - line.count("}")
            continue
        if cur is None:
            continue
        m = re.match(r"^location\s+(?:(=|~\*|~|\^~)\s+)?(\S+)\s*\{(.*)$", line)
        if m and loc is None:
            loc = {"modifier": m.group(1) or "", "path": m.group(2), "proxy_pass": None, "limit_req": False,
                   "limit_conn": False, "allow_deny": False}
            cur["locations"].append(loc)
            loc_depth = depth
            for part in m.group(3).split(";"):      # a location on one line: { proxy_pass ...; }
                part = part.strip().rstrip("}").strip()
                mp = re.match(r"^proxy_pass\s+(\S+)$", part)
                if mp:
                    loc["proxy_pass"] = mp.group(1)
                if part.startswith("limit_req ") or part.startswith("limit_req\t"):
                    loc["limit_req"] = True
                if part.startswith("limit_conn ") or part.startswith("limit_conn\t"):
                    loc["limit_conn"] = True
        elif loc is None:
            m = re.match(r"^server_name\s+([^;]+);", line)
            if m:
                cur["names"] += m.group(1).split()
            m = re.match(r"^listen\s+([^;]+);", line)
            if m:
                cur["listens"].append(m.group(1))
        else:
            m = re.match(r"^proxy_pass\s+([^;]+);", line)
            if m:
                loc["proxy_pass"] = m.group(1).strip()
            if line.startswith("limit_req ") or line.startswith("limit_req\t"):
                loc["limit_req"] = True
            if line.startswith("limit_conn ") or line.startswith("limit_conn\t"):
                loc["limit_conn"] = True
            if line.startswith("allow ") or line.startswith("deny "):
                loc["allow_deny"] = True
        depth += line.count("{") - line.count("}")
        if loc is not None and depth <= loc_depth:
            loc, loc_depth = None, None
        if depth <= 0:
            cur, loc, loc_depth = None, None, None
    return sites


def through_nginx(host: str, path: str, timeout=20) -> tuple[int, dict | None, float]:
    """GET https://HOST{path} through this machine's own nginx (the certificate checked for HOST)."""
    url = f"https://{host}{path}"
    t0 = time.time()
    code, out = run(CURL + ["-sS", "--max-time", str(timeout), "--resolve", f"{host}:443:127.0.0.1",
                            "-w", "\n%{http_code}", url], timeout=timeout + 5)
    took = time.time() - t0
    body, _, status = out.rpartition("\n")
    try:
        st = int(status.strip())
    except ValueError:
        return 0, None, took
    try:
        return st, json.loads(body), took
    except ValueError:
        return st, None, took


def brain(prefer_host: str = "xyberrp.duckdns.org") -> dict:
    """Where nginx serves the brain to players: every location naming capri-brain in a TLS site, asked for its
    models through nginx itself.  {"url", "host", "path", "proxy_pass", "limit_req", "models", "seconds"} of the one
    that answers (the players' host first); "url" stays in memory and in brain.url, never printed."""
    found = []
    for site in nginx_sites():
        tls = any("443" in l or "ssl" in l for l in site["listens"])
        for loc in site["locations"]:
            if "capri-brain" not in loc["path"] or loc["modifier"] in ("~", "~*"):
                continue
            for host in site["names"]:
                if host in ("_", "localhost") or not re.match(r"^[a-z0-9.-]+$", host):
                    continue
                found.append({"host": host, "path": loc["path"], "proxy_pass": loc["proxy_pass"], "tls": tls,
                              "limit_req": loc["limit_req"], "limit_conn": loc["limit_conn"],
                              "allow_deny": loc["allow_deny"], "file": site.get("file"),
                              "modifier": loc["modifier"]})
    if not found:
        raise Failed("nginx serves no location naming capri-brain: the brain is not published to players")
    found.sort(key=lambda b: (b["host"] != prefer_host, not b["tls"]))
    tried = []
    for b in found:
        base = b["path"] if b["path"].endswith("/") else b["path"] + "/"
        st, body, took = through_nginx(b["host"], base + "v1/models")
        ids = [m.get("id") for m in (body or {}).get("data") or [] if isinstance(m, dict)]
        tried.append(f"{b['host']}{clean(base)}v1/models -> {st or 'no answer'}")
        if b["tls"] and st == 200 and "capri-brain" in ids:
            b.update(url=f"https://{b['host']}{base}v1", models=ids, seconds=round(took, 2), base=base)
            return b
    raise Failed("the brain does not answer through nginx: " + "; ".join(tried))


def brain_unit(proxy_pass: str | None) -> dict:
    """The unit behind the brain's port (whoever listens there), how it runs (no key's value) and its last lines."""
    out = {}
    m = re.match(r"^https?://(?:127\.0\.0\.1|localhost|\[::1\]):(\d+)", proxy_pass or "")
    if not m:
        return out
    port = m.group(1)
    out["port"] = int(port)
    code, ss = run(["ss", "-ltnpH", "sport", "=", f":{port}"], timeout=10)
    pid = None
    m2 = re.search(r"pid=(\d+)", ss)
    if m2:
        pid = m2.group(1)
        out["pid"] = int(pid)
    unit = None
    if pid:
        try:
            for line in open(f"/proc/{pid}/cgroup", encoding="utf-8"):
                m3 = re.search(r"/([^/]+\.service)", line)
                if m3:
                    unit = m3.group(1)
        except OSError:
            pass
        try:
            out["process"] = b" ".join(open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")).decode(
                "utf-8", errors="replace").strip()[:200]
        except OSError:
            pass
    out["unit"] = unit
    if unit:
        code, show = run(SYSTEMCTL + ["show", unit, "-p", "ActiveState,ActiveEnterTimestamp,User,Environment,"
                                                      "EnvironmentFiles,Restart"], timeout=15)
        props = dict(l.split("=", 1) for l in show.splitlines() if "=" in l)
        out["state"] = f"{props.get('ActiveState', '?')} since {props.get('ActiveEnterTimestamp', '?')}"
        out["restart"] = props.get("Restart")
        env = []
        try:
            for item in shlex.split(props.get("Environment", "")):
                k, _, v = item.partition("=")
                env.append(f"{k}={'<hidden>' if KEYISH_RX.search(k) else v}")
        except ValueError:
            pass
        for f in re.findall(r"(/[^\s()]+)", props.get("EnvironmentFiles", "")):
            try:
                for line in open(f, encoding="utf-8", errors="replace"):
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.removeprefix("export ").partition("=")
                        env.append(f"{k.strip()}={'<hidden>' if KEYISH_RX.search(k) else v.strip()}")
            except OSError:
                pass
        out["settings"] = env
        code, j = run(["journalctl", "-u", unit, "-n", "600", "--no-pager", "-o", "short-iso"], timeout=20)
        out["chats"] = [l for l in j.splitlines() if "[capri-brain]" in l][-12:]
    try:
        out["health"] = http_json(f"http://127.0.0.1:{port}/health", timeout=5)
    except Exception as e:  # noqa: BLE001
        out["health"] = f"no answer ({e.__class__.__name__})"
    return out


def brain_client_addresses() -> set:
    """The client addresses of the brain's requests in the web server's logs (kept in memory, never printed)."""
    out = set()
    code, conf = run(NGINX + ["-T"], timeout=30)
    logs = ["/var/log/nginx/access.log", "/var/log/nginx/access.log.1"]
    for m in re.finditer(r"^\s*access_log\s+(/\S+?)[;\s]", conf, re.M):
        if m.group(1) not in logs:
            logs.append(m.group(1))
    for p in logs:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for l in f:
                    if "capri-brain-" in l:
                        out.add(l.split(" ", 1)[0])
        except OSError:
            continue
    return out


def access_log_counts(days: int = 2) -> dict:
    """The web server's access log lines for the brain's path: how many, their answers, from how many addresses
    (no address shown), the last ten (time, request without the secret, answer, bytes, request time if logged)."""
    logs = ["/var/log/nginx/access.log", "/var/log/nginx/access.log.1"]
    code, out = run(NGINX + ["-T"], timeout=30)
    for m in re.finditer(r"^\s*access_log\s+(/\S+?)[;\s]", out, re.M):
        if m.group(1) not in logs:
            logs.append(m.group(1))
    lines = []
    for p in logs:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines += [l.rstrip("\n") for l in f if "capri-brain-" in l]
        except OSError:
            continue
    rx = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+)')
    status, addrs, last = {}, set(), []
    for l in lines:
        m = rx.match(l)
        if not m:
            continue
        status[m.group(5)] = status.get(m.group(5), 0) + 1
        addrs.add(m.group(1))
        last.append(f"{m.group(2)} {m.group(3)} {clean(m.group(4))} -> {m.group(5)} ({m.group(6)} B)")
    return {"requests": sum(status.values()), "answers": status, "addresses": len(addrs), "last": last[-10:],
            "files": [p for p in logs if os.path.isfile(p)]}


def ollama() -> dict:
    out = {"state": unit_state("ollama.service")}
    code, lst = run(["ollama", "list"], timeout=20)
    out["models"] = [l.split()[0] for l in lst.splitlines()[1:] if l.strip()] if code == 0 else []
    code, ps = run(["ollama", "ps"], timeout=20)
    out["loaded"] = [re.sub(r"\s{2,}", "  ", l.strip()) for l in ps.splitlines() if l.strip()] if code == 0 else []
    code, show = run(SYSTEMCTL + ["show", "ollama.service", "-p", "Environment"], timeout=15)
    env = []
    try:
        for item in shlex.split(show.partition("=")[2]):
            k, _, v = item.partition("=")
            env.append(f"{k}={'<hidden>' if KEYISH_RX.search(k) else v}")
    except ValueError:
        pass
    out["settings"] = env
    return out


def machine() -> dict:
    out = {"host": socket.gethostname()}
    try:
        out["cpus"] = os.cpu_count()
        out["load"] = open("/proc/loadavg").read().split()[:3]
        mem = dict(re.findall(r"^(\w+):\s+(\d+)", open("/proc/meminfo").read(), re.M))
        out["memory_gb"] = round(int(mem.get("MemTotal", 0)) / 1048576, 1)
        out["available_gb"] = round(int(mem.get("MemAvailable", 0)) / 1048576, 1)
    except (OSError, ValueError):
        pass
    code, gpu = run(["nvidia-smi", "-L"], timeout=10)
    out["gpu"] = gpu.strip().splitlines()[:2] if code == 0 else "none (no nvidia-smi answer)"
    return out


# ------------------------------------------------------------------------------------------------ commands
def describe_role(role: str, cur_brain: dict | None) -> dict:
    name, world, root = role_paths(role)
    unit = name + ".service"
    text, cfg = load_cfg(root)
    rm = cfg.get("requiredMods") or {}
    entry = capri_entry(cfg)
    who = online(root)
    info = {"role": role, "world": world, "root": root, "unit": unit, "unit_state": unit_state(unit),
            "open77": open77_version(root), "online": len(who),
            "required_mods": {"enabled": rm.get("enabled") if isinstance(rm, dict) else None,
                              "unsecured": rm.get("unsecured") if isinstance(rm, dict) else None,
                              "packages": len(packages(cfg))}}
    say(f"===== {world} ({root}): Open77 {info['open77']}, {unit} {info['unit_state']}, "
        f"players on: {', '.join(who) if who else 'none'}")
    say(f"  requiredMods: enabled={info['required_mods']['enabled']} unsecured={info['required_mods']['unsecured']}, "
        f"{info['required_mods']['packages']} package(s)")
    if entry is None:
        say(f"  !! no {MOD_ID} entry: this server does not hand out Capri")
        info["entry"] = None
        return info
    info["entry"] = {k: entry.get(k) for k in ("version", "sha256", "sizeBytes", "source", "displayName")}
    say(f"  {MOD_ID}: {entry.get('version')} sha256 {str(entry.get('sha256'))[:16]}... {entry.get('sizeBytes')} B, "
        f"source {entry.get('source')}")
    blob = os.path.join(mods_dir(root, cfg), f"{entry.get('sha256')}.blob")
    if not os.path.isfile(blob):
        say(f"  !! its blob is not in the hosted store ({blob})")
        info["blob"] = "missing"
        return info
    ok = sha256_file(blob) == entry.get("sha256")
    look = zip_look(blob)
    info["blob"] = "ok" if ok else "hash differs"
    info["package"] = {k: v for k, v in look.items() if k != "url"}
    if look["wired"]:
        same = cur_brain is not None and look.get("url") == cur_brain.get("url")
        info["package"]["address"] = "the one nginx serves" if same else "NOT the one nginx serves"
        say(f"  its blob: {'sha ok' if ok else '!! hash differs'}, {look['files']} files; the brain IS wired in "
            f"({look.get('package')}, {look.get('world')}, host {look.get('host')}, {look['hook']}; address: "
            f"{info['package']['address']})")
    else:
        say(f"  its blob: {'sha ok' if ok else '!! hash differs'}, {look['files']} files; the brain is NOT wired in: "
            f"a player's Capri starts on Player2, her default (\"I'm here, V, but disconnected\")")
    port, man = manifest(cfg)
    if port:
        hit = next((m for m in man.get("mods") or man.get("packages") or [] if m.get("id") == MOD_ID), {})
        n, st = query_status(port)
        info["manifest"] = {"port": port, "version": hit.get("version"), "same_sha": hit.get("sha256") == entry.get("sha256"),
                            "enabled": man.get("enabled"), "unsecured": man.get("unsecured"), "players": n}
        say(f"  the manifest players get (port {port}): Capri {hit.get('version')}, "
            f"{'the same build' if info['manifest']['same_sha'] else '!! ANOTHER build than server.jsonc names (restart pending?)'}"
            f"; enabled={man.get('enabled')} unsecured={man.get('unsecured')}; players (query): {n}")
    else:
        say("  !! no local port answers the mod manifest with Capri in it")
    for l in last_start_lines(root, r"Required mods:|listening on UDP", 3):
        say("  log: " + l[:220])
    return info


def cmd_look(a) -> int:
    m = machine()
    say(f"who: {os.environ.get('USER') or 'root'} on {m.get('host')}: {m.get('cpus')} CPU(s), load {' '.join(m.get('load', []))}, "
        f"memory {m.get('available_gb')} of {m.get('memory_gb')} GB free; GPU: {m.get('gpu')}")
    out = {"machine": m}
    say("===== the brain (what players' Capri thinks with)")
    cur = None
    try:
        cur = brain()
        say(f"  nginx: {cur['host']}{clean(cur['base'])} ({'TLS' if cur['tls'] else 'NO TLS'}) -> {cur['proxy_pass']}; "
            f"per-address limits: limit_req {'on' if cur['limit_req'] else 'OFF'}, limit_conn "
            f"{'on' if cur['limit_conn'] else 'off'}, allow/deny {'on' if cur['allow_deny'] else 'off'}")
        say(f"  through this machine's nginx: v1/models -> 200 in {cur['seconds']} s: {', '.join(cur['models'])}")
        out["brain"] = {k: v for k, v in cur.items() if k not in ("url", "path", "base")}
    except Failed as e:
        say(f"  !! {e}")
        out["brain"] = {"error": str(e)}
    bu = brain_unit(cur.get("proxy_pass") if cur else None)
    if bu:
        say(f"  behind it, port {bu.get('port')}: unit {bu.get('unit')} ({bu.get('state', '?')}, Restart={bu.get('restart')})"
            f"; process: {bu.get('process', '?')}")
        for s in bu.get("settings") or []:
            say(f"    setting: {s}")
        h = bu.get("health")
        say(f"    health: {json.dumps(h)[:400] if isinstance(h, dict) else h}")
        say(f"    its last requests ({len(bu.get('chats') or [])}):")
        for l in bu.get("chats") or []:
            say("      " + l[:240])
        out["brain_unit"] = {k: v for k, v in bu.items() if k != "chats"}
    o = ollama()
    say(f"  Ollama: {o['state']}; models: {', '.join(o['models']) or 'none listed'}")
    for l in o["loaded"]:
        say(f"    loaded: {l}")
    for s in o["settings"]:
        say(f"    setting: {s}")
    out["ollama"] = o
    acc = access_log_counts()
    say(f"  the web server's log ({', '.join(acc['files']) or 'none found'}): {acc['requests']} request(s) to the brain, "
        f"answers {json.dumps(acc['answers'], sort_keys=True)}, from {acc['addresses']} address(es); the last ones:")
    for l in acc["last"]:
        say("    " + l)
    out["access"] = {k: v for k, v in acc.items() if k != "last"}
    say("===== her voice (Capri Voz on a PC without her local engine speaks with it)")
    try:
        vh = voice_local_health()
        vrec = voice_record()
        say(f"  {VOICE_UNIT}: {unit_state(VOICE_UNIT + '.service')}; installed by this kit: "
            f"{'yes, ' + str(vrec.get('versions')) if vrec.get('secret') else 'no'}")
        if isinstance(vh, dict):
            say(f"  health: languages {json.dumps(vh.get('languages'))[:300]}; {vh.get('spoken')} line(s) said, "
                f"{vh.get('errors')} error(s), {vh.get('busy_refused')} refused busy, average {vh.get('avg_gen_ms')} ms "
                f"to make one; up {vh.get('uptime_s')} s")
        if cur:
            now = voice_now(cur["host"])
            say("  through nginx: " + (f"answers ({now['languages']}, {now['seconds']} s)" if now.get("url")
                                         else f"no ({now.get('why')})"))
        code, j = run(["journalctl", "-u", VOICE_UNIT, "-n", "400", "--no-pager", "-o", "short-iso"], timeout=30)
        speaks = [l for l in j.splitlines() if " speak " in l]
        say(f"  its last requests ({len(speaks)} in the journal's last 400 lines):")
        for l in speaks[-8:]:
            say("    " + l[:220])
    except (Failed, OSError) as e:
        say(f"  !! {e}")
    say("===== Mass Override's gates (every game polls its own; casts are handed to everyone)")
    for role in ("staging", "production"):
        folder, gunit, gport, public = gate_paths(role)
        gs = gate_state(role)
        say(f"  {ROLES[role][1]}: {gunit} {unit_state(gunit + '.service')}; GET /casts: "
            f"{'yes' if gate_ask(gport, '/casts?since=0')[0] == 200 else 'NO (an older gate)'}; games polling: "
            f"{gs.get('polling', '?')}; casts: {json.dumps(gs.get('recent') or [])[:300]}")
        code, j = run(["journalctl", "-u", gunit, "-n", "300", "--no-pager", "-o", "cat"], timeout=30)
        for l in [x for x in j.splitlines() if x.startswith("[cast]") or x.startswith("[feed]")
                  or '"phase":"remote' in x][-8:]:
            say("    " + l[:260])
    out["roles"] = []
    for role in [r.strip() for r in (a.roles or "staging,production").split(",") if r.strip()]:
        try:
            out["roles"].append(describe_role(role, cur))
        except (Failed, OSError, ValueError) as e:
            say(f"===== {role}: !! {e}")
            out["roles"].append({"role": role, "error": str(e)})
    result(command="look", **out)
    return 0


def sweep_old_work(here: str, hours: float = 2.0) -> None:
    """This kit's own work folders left behind by a run that was stopped (an upload cut off, a closed window):
    /tmp/avkit-* folders holding capri_server.py, older than HOURS -- never this run's, never anything else."""
    base = os.path.dirname(os.path.abspath(here))
    try:
        names = os.listdir(base)
    except OSError:
        return
    gone = 0
    for n in names:
        d = os.path.join(base, n)
        if not n.startswith("avkit-") or os.path.abspath(d) == os.path.abspath(here) or os.path.islink(d):
            continue
        try:
            if os.path.isfile(os.path.join(d, "capri_server.py")) and time.time() - os.path.getmtime(d) > hours * 3600:
                shutil.rmtree(d)
                gone += 1
        except OSError:
            continue
    if gone:
        say(f"(the machine's /tmp: {gone} work folder(s) of earlier runs of this kit that were stopped, removed)")


def cmd_fetch(a) -> int:
    sweep_old_work(a.work)
    name, world, root = role_paths(a.role)
    text, cfg = load_cfg(root)
    entry = capri_entry(cfg)
    if entry is None:
        raise Failed(f"{world} has no {MOD_ID} entry in requiredMods")
    sha = entry.get("sha256") or ""
    blob = os.path.join(mods_dir(root, cfg), f"{sha}.blob")
    if not os.path.isfile(blob) or sha256_file(blob) != sha:
        raise Failed(f"{world}: the blob of {entry.get('version')} is not in the hosted store, or hashes otherwise")
    cur = brain()
    os.makedirs(a.work, exist_ok=True)
    shutil.copyfile(blob, os.path.join(a.work, "capri-current.zip"))
    os.chmod(os.path.join(a.work, "capri-current.zip"), 0o644)
    # what the PC needs to build and check (its scripts) and to say what the build must hold (every file's hash):
    # a few hundred KB instead of the whole package -- a slow uplink sends 26 MB at 13 KB/s (2026-11-12)
    files = read_entries(blob)
    with zipfile.ZipFile(os.path.join(a.work, "scripts.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in sorted(files):
            if (n.startswith("r6/scripts/") and n.endswith(".reds")) or n in EDITABLE_OTHER:
                info = zipfile.ZipInfo(n, FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, files[n])
    with open(os.path.join(a.work, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"sha256": sha, "entries": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}, f)
    fd = os.open(os.path.join(a.work, "brain.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(cur["url"] + "\n")
    voice = voice_now(cur["host"])
    if voice.get("url"):
        fd = os.open(os.path.join(a.work, "voice.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(voice["url"] + "\n")
    look = zip_look(blob)
    who = online(root)
    say(f"{world}: Capri {entry.get('version')} ({look['files']} files, sha256 {sha[:16]}...) copied for the build; "
        f"the brain wired in already: {'yes, ' + ('the same address' if look.get('url') == cur['url'] else 'ANOTHER address') if look['wired'] else 'no'}"
        f"; players on: {len(who)}")
    say(f"the brain for players: {cur['host']}{clean(cur['base'])}v1 answers through nginx ({', '.join(cur['models'])})")
    say(f"her voice for players: " + (f"{cur['host']}/capri-voice-<secret>/v1 answers through nginx "
                                       f"({voice.get('languages')})" if voice.get("url") else
                                       f"not on this machine yet ({voice.get('why')})"))
    result(command="fetch", role=a.role, world=world, root=root, unit=name + ".service",
           entry={k: entry.get(k) for k in ("version", "sha256", "sizeBytes", "displayName")},
           wired=look["wired"], wired_same=bool(look["wired"] and look.get("url") == cur["url"]),
           host=cur["host"], online=len(who), limit_req=cur["limit_req"],
           voice={k: v for k, v in voice.items() if k != "url"})
    return 0


FIXED_TIME = (2026, 1, 1, 0, 0, 0)
CAPRI_SCRIPTS = "r6/scripts/CapriPersonalityConstruct/"
# besides Capri's scripts, what a build may change or add: Mass Override's own script, and Capri Voz speaking with
# her voice from this machine (its program for Windows and for Linux, and where that voice answers)
EDITABLE_OTHER = ("r6/scripts/Open77/Open77MassOverride.reds",
                  CAPRIVOZ + "CapriVoz.ps1", CAPRIVOZ + "linux/capri_voz_linux.py", CAPRIVOZ + "servidor.json")


def read_entries(path: str) -> dict:
    """A package's files by game-root path (folders left out); a path that climbs out, or twice, refused."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            n = info.filename.replace("\\", "/").lstrip("./")
            if not n or n.startswith("/") or ".." in n.split("/") or (len(n) > 1 and n[1] == ":"):
                raise Failed(f"the package has a path that climbs out: {n!r}")
            if n in out:
                raise Failed(f"the package has {n!r} twice")
            out[n] = z.read(info)
    return out


def write_entries(path: str, entries: dict) -> None:
    """Reproducible: sorted, one fixed time, deflate 6 (as the kit's builder and the release scripts write)."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for n in sorted(entries):
            info = zipfile.ZipInfo(n, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            z.writestr(info, entries[n])
    os.replace(tmp, path)


def cmd_assemble(a) -> int:
    """The new package made here, from the live one (WORK/capri-current.zip, which must still be --expect-sha) and the
    PC's few changed scripts (--delta, only under r6/scripts/CapriPersonalityConstruct/): every file of the result
    must hash to what the PC built and compiled (--expect, a JSON {path: sha256} of the whole package), nothing more,
    nothing less.  Writes WORK/assembled.zip."""
    live = os.path.join(a.work, "capri-current.zip")
    if not os.path.isfile(live) or sha256_file(live) != a.expect_sha:
        raise Failed("the live package copied for this build is not the one the build was made from")
    entries = read_entries(live)
    delta = read_entries(a.delta)
    for n in delta:
        if not ((n.startswith(CAPRI_SCRIPTS) and n.endswith(".reds")) or n in EDITABLE_OTHER):
            raise Failed(f"the changes name a file a build may not change: {n!r}")
    entries.update(delta)
    want = json.load(open(a.expect, encoding="utf-8"))
    have = {n: hashlib.sha256(b).hexdigest() for n, b in entries.items()}
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    wrong = sorted(n for n in want if n in have and have[n] != want[n])
    if missing or extra or wrong:
        raise Failed(f"the package made here is not the one the PC built and compiled: missing {missing[:3]}, "
                     f"more {extra[:3]}, different {wrong[:3]}")
    out = os.path.join(a.work, "assembled.zip")
    write_entries(out, entries)
    back = read_entries(out)
    if {n: hashlib.sha256(b).hexdigest() for n, b in back.items()} != want:
        raise Failed("the package written here does not read back as built")
    sha, size = sha256_file(out), os.path.getsize(out)
    say(f"the new package made on the machine: {len(back)} files ({len(delta)} changed or new from the PC, the rest "
        f"from the live package), every file as the PC built and compiled it; sha256 {sha[:16]}..., {size} B")
    result(command="assemble", sha256=sha, sizeBytes=size, files=len(back), changed=sorted(delta))
    return 0


def record_path(role: str) -> str:
    return os.path.join(STATE_DIR, f"{role}.json")


def load_record(role: str) -> dict:
    try:
        return json.load(open(record_path(role), encoding="utf-8"))
    except (OSError, ValueError):
        return {"role": role, "history": []}


def save_record(role: str, rec: dict) -> None:
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    tmp = record_path(role) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
    os.replace(tmp, record_path(role))


def point_entry(root: str, text: str, version: str, sha: str, size: int) -> tuple[str, dict]:
    """server.jsonc's Capri entry pointed at (version, sha, size): only those three values change, which is then
    checked by reading both texts as JSON."""
    start, end = entry_span(text)
    block = text[start:end]
    new = block
    for key, rx, val in (("version", r'("version"\s*:\s*")([^"]*)(")', version),
                         ("sha256", r'("sha256"\s*:\s*")([0-9a-fA-F]{64})(")', sha)):
        if len(re.findall(rx, new)) != 1:
            raise Failed(f"the Capri entry does not have exactly one \"{key}\"")
        new = re.sub(rx, lambda m: m.group(1) + val + m.group(3), new, count=1)
    if len(re.findall(r'("sizeBytes"\s*:\s*)(\d+)', new)) != 1:
        raise Failed('the Capri entry does not have exactly one "sizeBytes"')
    new = re.sub(r'("sizeBytes"\s*:\s*)(\d+)', lambda m: m.group(1) + str(size), new, count=1)
    out = text[:start] + new + text[end:]
    old_cfg, new_cfg = json.loads(strip_jsonc(text)), json.loads(strip_jsonc(out))
    e = capri_entry(new_cfg)
    if not e or e.get("version") != version or e.get("sha256") != sha or e.get("sizeBytes") != size:
        raise Failed("server.jsonc read back does not name the new build")
    for c in (old_cfg, new_cfg):
        x = capri_entry(c)
        for k in ("version", "sha256", "sizeBytes"):
            x.pop(k, None)
    if old_cfg != new_cfg:
        raise Failed("the edit would change more of server.jsonc than the Capri entry's build")
    return out, e


def write_config(root: str, text: str) -> None:
    """server.jsonc replaced in one step (its mode and owner kept)."""
    path = os.path.join(root, "server.jsonc")
    tmp = path + ".capri-kit.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copymode(path, tmp)
    st = os.stat(path)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    os.replace(tmp, path)


def import_zip(root: str, cfg: dict, zip_path: str, version: str, old_entry: dict) -> tuple[str, int, str]:
    sha = sha256_file(zip_path)
    size = os.path.getsize(zip_path)
    store = mods_dir(root, cfg)
    if not os.path.isdir(store):
        raise Failed(f"the hosted store {store} is not there")
    blob = os.path.join(store, f"{sha}.blob")
    if not os.path.exists(blob):
        tmp = blob + ".tmp"
        shutil.copyfile(zip_path, tmp)
        os.replace(tmp, blob)
    if sha256_file(blob) != sha:
        raise Failed("the copy in the hosted store hashes otherwise")
    side = os.path.join(store, f"{old_entry.get('sha256')}.json")
    try:
        doc = json.load(open(side, encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    doc.update({"id": MOD_ID, "version": version, "displayName": old_entry.get("displayName") or doc.get("displayName"),
                "fileName": os.path.basename(zip_path), "sha256": sha, "sizeBytes": size,
                "capability": doc.get("capability") or "executable",
                "importedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(), "reviewRequestedAtUtc": None})
    with open(os.path.join(store, f"{sha}.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    return sha, size, blob


def cmd_import(a) -> int:
    name, world, root = role_paths(a.role)
    unit = name + ".service"
    text, cfg = load_cfg(root)
    entry = capri_entry(cfg)
    if entry is None:
        raise Failed(f"{world} has no {MOD_ID} entry")
    if entry.get("sha256") != a.expect_sha:
        say(f"{world}: its Capri is no longer the build this one was made from ({str(entry.get('sha256'))[:16]}... now, "
            f"{a.expect_sha[:16]}... then): NOTHING changed -- run the bat again, it builds from what is live")
        result(command="import", role=a.role, changed=False, why="the live build changed")
        return NO
    who = online(root)
    if who and not a.force:
        say(f"{world}: connection(s) {', '.join(who)} online: NOTHING changed (the new build reaches players at the "
            f"restart; leave the server and run the bat again)")
        result(command="import", role=a.role, changed=False, why="players on", online=len(who))
        return NO
    with zipfile.ZipFile(a.zip) as z:
        if TARGET not in z.namelist():
            raise Failed("the build has no Capri.ServerBrain.reds")
    sha, size, blob = import_zip(root, cfg, a.zip, a.version, entry)
    say(f"{world}: the build is in the hosted store: {os.path.basename(blob)} ({size} B)")
    new_text, new_entry = point_entry(root, text, a.version, sha, size)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup = os.path.join(root, f"server.jsonc.before-capri-kit-{a.version}-{ts}")
    shutil.copy2(os.path.join(root, "server.jsonc"), backup)
    write_config(root, new_text)
    say(f"{world}: server.jsonc names Capri {a.version} now (kept first: {os.path.basename(backup)}); only the entry's "
        f"version, sha256 and sizeBytes changed")
    code, out = check_config(unit, root)
    if code != 0:
        shutil.copy2(backup, os.path.join(root, "server.jsonc"))
        say(f"{world}: !! the server's own --check-config refused it (exit {code}); server.jsonc PUT BACK:")
        say("  " + out.replace("\n", "\n  "))
        result(command="import", role=a.role, changed=False, why="check-config refused", check=out[-400:])
        return 1
    say(f"{world}: the server's own --check-config accepts it: {out.splitlines()[-1][:160] if out.strip() else 'ok'}")
    rec = load_record(a.role)
    rec["history"].append({"at": ts, "backup": backup, "world": world,
                           "from": {k: entry.get(k) for k in ("version", "sha256", "sizeBytes")},
                           "to": {"version": a.version, "sha256": sha, "sizeBytes": size}})
    save_record(a.role, rec)
    result(command="import", role=a.role, changed=True, version=a.version, sha256=sha, sizeBytes=size,
           backup=os.path.basename(backup), previous=rec["history"][-1]["from"])
    return 0


def cmd_verify(a) -> int:
    name, world, root = role_paths(a.role)
    text, cfg = load_cfg(root)
    problems = []
    entry = capri_entry(cfg) or {}
    if a.sha == "live":
        # whatever server.jsonc names now (a build this kit did not record here)
        a.sha, a.version = entry.get("sha256") or "", entry.get("version") or ""
        say(f"{world}: checking the build server.jsonc names now: {a.version} sha256 {a.sha[:16]}...")
    if entry.get("sha256") != a.sha or entry.get("version") != a.version:
        problems.append(f"server.jsonc names {entry.get('version')} {str(entry.get('sha256'))[:16]}..., "
                        f"not {a.version} {a.sha[:16]}...")
    port, man = manifest(cfg, want_sha=a.sha)
    if not port:
        problems.append("no local port hands out a manifest with this build (the server not restarted yet?)")
        hit = {}
    else:
        hit = next((m for m in man.get("mods") or man.get("packages") or [] if m.get("id") == MOD_ID), {})
        if hit.get("version") != a.version:
            problems.append(f"the manifest says version {hit.get('version')}")
        if man.get("enabled") is False:
            problems.append("the manifest says requiredMods are not enabled")
        if man.get("unsecured") is False:
            problems.append("the manifest says unsecured is off: the launcher refuses Capri's DLL from a secure world")
        say(f"{world}: the manifest players get (port {port}) names Capri {hit.get('version')} sha256 {a.sha[:16]}...; "
            f"enabled={man.get('enabled')} unsecured={man.get('unsecured')}")
    look = {}
    if port:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/mods/v1/blobs/{a.sha}", timeout=120) as r:
                payload = r.read()
            if hashlib.sha256(payload).hexdigest() != a.sha:
                problems.append("the blob the server hands out hashes otherwise")
            look = zip_look(payload)
            say(f"{world}: the blob it hands out: {len(payload)} B, sha ok: {hashlib.sha256(payload).hexdigest() == a.sha}, "
                f"{look.get('files')} files")
        except Exception as e:  # noqa: BLE001
            problems.append(f"the blob could not be fetched from the server: {e.__class__.__name__}")
    try:
        cur = brain()
    except Failed as e:
        cur = None
        problems.append(str(e))
    if look:
        if not look.get("wired"):
            problems.append("the package handed out has no Capri.ServerBrain.reds")
        else:
            same = cur is not None and look.get("url") == cur.get("url")
            if not same:
                problems.append("the script's brain address is not the one nginx serves now")
            if look.get("package") != a.version or look.get("world") != world:
                problems.append(f"the script says {look.get('package')} / {look.get('world')}")
            say(f"{world}: its Capri.ServerBrain.reds: {look.get('package')}, {look.get('world')}, host {look.get('host')}, "
                f"model {look.get('model')}, hook {look.get('hook')}; the address: "
                f"{'the one nginx serves now' if same else 'NOT the one nginx serves'}")
    if cur:
        say(f"the brain through nginx: v1/models -> 200 in {cur['seconds']} s ({', '.join(cur['models'])})")
        # her voice: the package names the voice nginx serves now, and it answers
        now = voice_now(cur["host"])
        if look:
            if not look.get("voice_url"):
                problems.append("the package handed out has no servidor.json: players' Capri Voz has no server voice")
            elif not now.get("url"):
                problems.append(f"her voice does not answer through nginx: {now.get('why')}")
            elif look.get("voice_url") != now.get("url"):
                problems.append("the package's servidor.json names another voice than nginx serves now")
            else:
                say(f"{world}: its servidor.json names her voice as nginx serves it now ({now['languages']}, answered "
                    f"in {now['seconds']} s); Capri Voz {'carries' if look.get('voz_patched') else 'does NOT carry'} "
                    f"the server voice")
            if not look.get("voz_patched"):
                problems.append("the package's CapriVoz.ps1 does not use the server voice")
        if now.get("url"):
            fd = os.open(os.path.join(a.work, "voice.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(now["url"] + "\n")
        # Mass Override: the package's gate is this role's, and the gate hands every game the casts
        folder, gunit, gport, public = gate_paths(a.role)
        want_base = f"https://{cur['host']}{public.rstrip('/')}"
        if look:
            if look.get("mo_base") != want_base:
                problems.append(f"the package's Mass Override talks to {look.get('mo_base')}, not {want_base}")
            if not look.get("mo_everyone"):
                problems.append("the package's Mass Override does not run other players' casts (MassOverrideRemote)")
        nst, ntext = through_nginx_text(cur["host"], public + "casts?since=0&session=capri-kit-verify")
        if nst != 200:
            problems.append(f"the gate does not hand out casts through nginx ({public}casts -> {nst})")
        else:
            gs = gate_state(a.role)
            say(f"{world}: Mass Override talks to {look.get('mo_base')} (build {look.get('mo_build')}, "
                f"{'every player runs every cast' if look.get('mo_everyone') else 'caster only'}); the gate hands out "
                f"casts through nginx; {gs.get('polling', '?')} game(s) polling it now")
    for l in last_start_lines(root, r"Required mods:|listening on UDP", 3):
        say("  log: " + l[:220])
    for p in problems:
        say(f"!! {p}")
    result(command="verify", role=a.role, ok=not problems, problems=problems, version=a.version, sha256=a.sha)
    return 0 if not problems else 1


def cmd_putback(a) -> int:
    name, world, root = role_paths(a.role)
    unit = name + ".service"
    rec = load_record(a.role)
    if not rec["history"]:
        say(f"{world}: this kit never changed its Capri: nothing to put back")
        result(command="putback", role=a.role, changed=False, why="nothing recorded")
        return NO
    last = rec["history"][-1]
    text, cfg = load_cfg(root)
    entry = capri_entry(cfg) or {}
    if entry.get("sha256") != last["to"]["sha256"]:
        say(f"{world}: its Capri is no longer the build this kit put there ({entry.get('version')} now): NOTHING changed")
        result(command="putback", role=a.role, changed=False, why="the live build changed since")
        return NO
    who = online(root)
    if who and not a.force:
        say(f"{world}: connection(s) {', '.join(who)} online: NOTHING changed (leave the server and run the bat again)")
        result(command="putback", role=a.role, changed=False, why="players on", online=len(who))
        return NO
    prev = last["from"]
    blob = os.path.join(mods_dir(root, cfg), f"{prev['sha256']}.blob")
    if not os.path.isfile(blob) or sha256_file(blob) != prev["sha256"]:
        raise Failed(f"the earlier build's blob ({prev['version']}) is not in the hosted store any more")
    new_text, _ = point_entry(root, text, prev["version"], prev["sha256"], int(prev["sizeBytes"]))
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup = os.path.join(root, f"server.jsonc.before-capri-kit-putback-{ts}")
    shutil.copy2(os.path.join(root, "server.jsonc"), backup)
    write_config(root, new_text)
    code, out = check_config(unit, root)
    if code != 0:
        shutil.copy2(backup, os.path.join(root, "server.jsonc"))
        say(f"{world}: !! --check-config refused the put-back (exit {code}); server.jsonc left as it was")
        result(command="putback", role=a.role, changed=False, why="check-config refused")
        return 1
    rec["history"].pop()
    rec.setdefault("undone", []).append(dict(last, undoneAt=ts))
    save_record(a.role, rec)
    say(f"{world}: Capri {prev['version']} again (sha256 {prev['sha256'][:16]}...); kept first: {os.path.basename(backup)}")
    result(command="putback", role=a.role, changed=True, version=prev["version"], sha256=prev["sha256"])
    return 0


# ------------------------------------------------------------------------------------------------ the brain's limits
GUARD_RATE = "12r/m"        # one address: a dozen questions at once, then one every five seconds
GUARD_BURST = 12
GUARD_CONN = 4              # questions in flight at once from one address (each one takes half a minute)
GUARD_MARK = "# XyberRP Capri kit: per-address limits"
ZONE_LINES = (f"{GUARD_MARK} for the brain (its private address travels in the Capri package to every player)\n"
              f"limit_req_zone $binary_remote_addr zone=capri_brain:1m rate={GUARD_RATE};\n"
              f"limit_conn_zone $binary_remote_addr zone=capri_brain_conn:1m;\n")
LOCATION_LINES = ("{indent}    {mark}\n"
                  f"{{indent}}    limit_req zone=capri_brain burst={GUARD_BURST} nodelay;\n"
                  "{indent}    limit_req_status 429;\n"
                  f"{{indent}}    limit_conn capri_brain_conn {GUARD_CONN};\n"
                  "{indent}    limit_conn_status 429;\n")


INLINE_LIMITS = (f"limit_req zone=capri_brain burst={GUARD_BURST} nodelay; limit_req_status 429; "
                 f"limit_conn capri_brain_conn {GUARD_CONN}; limit_conn_status 429;")


def nginx_reload() -> tuple[int, str]:
    code, out = run(SYSTEMCTL + ["reload", "nginx"], timeout=60)
    if code != 0:
        code, out = run(NGINX + ["-s", "reload"], timeout=60)
    time.sleep(1.5)
    return code, out


def guard_record() -> dict:
    try:
        return json.load(open(os.path.join(STATE_DIR, "guard.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cmd_guard(a) -> int:
    """Per-address limits on the brain's nginx location (limit_req, limit_conn, answered 429): the brain's private
    address now travels to every player who joins, and the brain shares the machine's processors with the game
    servers.  The site file is kept first (STATE_DIR/nginx/), nginx -t must pass, nginx is reloaded, the brain is
    asked through nginx again -- anything wrong: the file is put back and nginx reloaded."""
    cur = brain()
    if cur["limit_req"]:
        say(f"the brain's location already has a per-address limit (limit_req): nothing changed")
        result(command="guard", changed=False, why="already limited")
        return NO
    conf = cur.get("file")
    if not conf or not os.path.isfile(conf):
        raise Failed("nginx -T does not say which file holds the brain's location")
    real = os.path.realpath(conf)
    text = open(real, encoding="utf-8").read()
    # players must reach nginx with their own addresses: behind a proxy (loopback or private addresses in its log)
    # one limit would hold every player at once
    addrs = brain_client_addresses()
    if addrs and all(re.match(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|::1$|f[cd])", x) for x in addrs):
        say(f"!! every request in the web server's log reaches the brain from a loopback or private address "
            f"({len(addrs)} of them): something stands in front of nginx, and a per-address limit would hold every "
            f"player at once -- NOTHING changed")
        result(command="guard", changed=False, why="proxied")
        return 1
    # its opening, wherever the brace is: on a line of its own after it, or the whole location on one line --
    # XyberRP's site writes it on one line ("location /capri-brain-.../ { proxy_pass ...; }"), which the first
    # version of this step did not expect (2026-11-12: "there 0 times")
    hits = list(location_rx(cur["path"], cur["modifier"]).finditer(text))
    if len(hits) != 1:
        raise Failed(f"{real}: the brain's location is there {len(hits)} times (one expected)")
    code, all_conf = run(NGINX + ["-T"], timeout=30)
    zone_there = re.search(r"^\s*limit_req_zone\s.*zone=capri_brain:", all_conf, re.M) is not None
    conn_there = re.search(r"^\s*limit_conn_zone\s.*zone=capri_brain_conn:", all_conf, re.M) is not None
    if zone_there != conn_there:
        raise Failed("one of the two capri_brain zones is defined elsewhere, the other not: nothing changed")
    m = hits[0]
    eol = text.find("\n", m.end())
    rest = text[m.end(): eol if eol >= 0 else len(text)]
    if rest.strip():
        # the location on one line: the limits go into it right after its brace, the mark on a line above it
        new = (text[:m.start()] + f"{m.group(1)}{GUARD_MARK} (in the location below)\n" + text[m.start():m.end()]
               + " " + INLINE_LIMITS + text[m.end():])
        say(f"(the brain's location is on one line in {real}: the limits go into that line)")
    else:
        new = text[:m.end()] + "\n" + LOCATION_LINES.format(indent=m.group(1), mark=GUARD_MARK).rstrip("\n") + text[m.end():]
    if not zone_there:
        new = ZONE_LINES + "\n" + new
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    keep = os.path.join(STATE_DIR, "nginx")
    os.makedirs(keep, mode=0o700, exist_ok=True)
    backup = os.path.join(keep, os.path.basename(real) + ".before-capri-kit-" + ts)
    shutil.copy2(real, backup)
    st = os.stat(real)
    tmp = real + ".capri-kit.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.chmod(tmp, st.st_mode & 0o7777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    os.replace(tmp, real)
    say(f"{real}: the brain's location limited per address (limit_req {GUARD_RATE} burst {GUARD_BURST}, limit_conn "
        f"{GUARD_CONN}, both answered 429){'' if zone_there else '; its two zones defined at the top of the file'}; "
        f"kept first: {backup}")

    def put_back(why):
        shutil.copy2(backup, real)
        c1, o1 = run(NGINX + ["-t"], timeout=30)
        c2, o2 = nginx_reload() if c1 == 0 else (c1, o1)
        say(f"!! {why}: {real} PUT BACK (nginx -t {'ok' if c1 == 0 else 'FAILED'}, reload exit {c2})")
        result(command="guard", changed=False, why=why)
        return 1
    code, out = run(NGINX + ["-t"], timeout=30)
    if code != 0:
        say("  " + "\n  ".join(out.strip().splitlines()[-4:]))
        return put_back("nginx -t refused it")
    code, out = nginx_reload()
    if code != 0:
        return put_back(f"nginx did not reload ({out.strip()[-200:]})")
    try:
        again = brain()
    except Failed as e:
        return put_back(f"the brain does not answer through nginx after it ({e})")
    if not again["limit_req"]:
        return put_back("nginx -T does not show the limit in the brain's location")
    rec = guard_record()
    rec.setdefault("history", []).append({"at": ts, "file": real, "backup": backup,
                                          "sha256": hashlib.sha256(new.encode("utf-8")).hexdigest()})
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    with open(os.path.join(STATE_DIR, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    say(f"nginx reloaded; the brain answers through it with the limit on: v1/models -> 200 in {again['seconds']} s")
    result(command="guard", changed=True, file=real, backup=backup)
    return 0


def cmd_guard_putback(a) -> int:
    rec = guard_record()
    if not rec.get("history"):
        say("this kit never limited the brain's location: nothing to put back")
        result(command="guard-putback", changed=False, why="nothing recorded")
        return NO
    last = rec["history"][-1]
    real = last["file"]
    now = open(real, "rb").read()
    if hashlib.sha256(now).hexdigest() != last["sha256"]:
        say(f"{real} changed since this kit limited it: NOTHING changed")
        result(command="guard-putback", changed=False, why="the file changed since")
        return NO
    keep = os.path.join(STATE_DIR, "nginx", os.path.basename(real) + ".before-putback-"
                        + time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    shutil.copy2(real, keep)
    shutil.copy2(last["backup"], real)
    code, out = run(NGINX + ["-t"], timeout=30)
    if code != 0:
        shutil.copy2(keep, real)
        say("!! nginx -t refused the file as it was: left with the limits")
        result(command="guard-putback", changed=False, why="nginx -t refused")
        return 1
    nginx_reload()
    rec["history"].pop()
    with open(os.path.join(STATE_DIR, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    say(f"{real} as it was before the limits; nginx reloaded")
    result(command="guard-putback", changed=True, file=real)
    return 0



# ------------------------------------------------------------------------------------------------ nginx locations
def location_rx(path: str, modifier: str = "") -> re.Pattern:
    """A location's opening in a site file, its brace on the same line or the next; group 1 its indentation."""
    mod = (re.escape(modifier) + r"\s+") if modifier else ""
    return re.compile(r"(?m)^([ \t]*)location\s+" + mod + re.escape(path) + r"\s*\{")


def write_site(real: str, text: str) -> None:
    st = os.stat(real)
    tmp = real + ".capri-kit.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, st.st_mode & 0o7777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    os.replace(tmp, real)


def keep_site(real: str, why: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    keep = os.path.join(STATE_DIR, "nginx")
    os.makedirs(keep, mode=0o700, exist_ok=True)
    backup = os.path.join(keep, os.path.basename(real) + f".before-capri-kit-{why}-" + ts)
    shutil.copy2(real, backup)
    return backup


# ------------------------------------------------------------------------------------------------ her voice
def voice_record() -> dict:
    try:
        return json.load(open(os.path.join(STATE_DIR, "voice.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_voice_record(rec: dict) -> None:
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(STATE_DIR, "voice.json")
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
    os.replace(path + ".tmp", path)


def voice_locations() -> list[dict]:
    """Every nginx location serving her voice (a path starting /capri-voice-) in a TLS site: host, path, file."""
    out = []
    for site in nginx_sites():
        tls = any("443" in l or "ssl" in l for l in site["listens"])
        for loc in site["locations"]:
            if loc["path"].startswith("/capri-voice-") and tls:
                for host in site["names"]:
                    if re.match(r"^[a-z0-9.-]+$", host) and host not in ("_", "localhost"):
                        out.append({"host": host, "path": loc["path"], "proxy_pass": loc["proxy_pass"],
                                    "limit_req": loc["limit_req"], "file": site.get("file")})
    return out


def voice_local_health(timeout=5):
    try:
        return http_json(f"http://127.0.0.1:{VOICE_PORT}/health", timeout=timeout)
    except Exception:  # noqa: BLE001
        return None


def voice_now(host: str) -> dict:
    """Her voice as players reach it now: {"url" (kept off every log), "languages", "why" when not there}."""
    rec = voice_record()
    locs = [l for l in voice_locations() if l["host"] == host]
    if not rec.get("secret") or not locs:
        return {"why": "not installed by this kit" if not rec.get("secret") else "nginx serves no voice location"}
    loc = next((l for l in locs if l["path"].rstrip("/") == "/" + rec["secret"]), None)
    if loc is None:
        return {"why": "nginx serves another voice path than this kit's record"}
    st, body, took = through_nginx(host, "/" + rec["secret"] + "/health", timeout=15)
    if st != 200 or not isinstance(body, dict) or body.get("service") != "capri-voice":
        return {"why": f"it does not answer through nginx ({st or 'no answer'})"}
    langs = ",".join(sorted(k for k, v in (body.get("languages") or {}).items() if (v or {}).get("voice") == "capri"))
    return {"url": f"https://{host}/{rec['secret']}/v1", "languages": langs or "none loaded",
            "spoken": body.get("spoken"), "seconds": round(took, 2), "pocket_tts": body.get("pocket_tts")}


def machine_facts() -> dict:
    out = {}
    try:
        for line in open("/etc/os-release", encoding="utf-8"):
            if line.startswith("PRETTY_NAME="):
                out["os"] = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    out["cpus"] = os.cpu_count()
    try:
        mem = dict(re.findall(r"^(\w+):\s+(\d+)", open("/proc/meminfo").read(), re.M))
        out["memory_gb"] = round(int(mem.get("MemTotal", 0)) / 1048576, 1)
        out["available_gb"] = round(int(mem.get("MemAvailable", 0)) / 1048576, 1)
    except (OSError, ValueError):
        pass
    try:
        parent = VOICE_ROOT
        while not os.path.exists(parent):
            parent = os.path.dirname(parent)
        du = shutil.disk_usage(parent)
        out["disk_free_gb"] = round(du.free / 1e9, 1)
    except OSError:
        pass
    try:
        out["load"] = " ".join(open("/proc/loadavg").read().split()[:3])
    except OSError:
        pass
    return out


def pick_python() -> tuple[str, str]:
    """The Python her voice's venv is made with: the system's (3.10-3.14, with venv and ensurepip), else a fixed
    standalone CPython (STANDALONE_VERSION, hash checked) in VOICE_ROOT/python."""
    if VOICE_PYTHON:
        return VOICE_PYTHON, "given"
    for cand in ("python3.12", "python3.11", "python3.13", "python3.10", "python3"):
        p = shutil.which(cand)
        if not p:
            continue
        code, out = run([p, "-c", "import sys, ensurepip, venv; print('%d.%d' % sys.version_info[:2])"], timeout=60)
        ver = out.strip().splitlines()[-1] if out.strip() else ""
        if code == 0 and re.match(r"^3\.(1[0-4])$", ver):
            return p, f"the system's {cand} ({ver})"
        say(f"  {cand} ({p}): not usable for a venv ({(ver or out.strip()[-120:]) or code})")
    py = os.path.join(VOICE_ROOT, "python", "bin", "python3")
    if os.path.isfile(py):
        return py, f"the standalone CPython {STANDALONE_VERSION} kept in " + os.path.join(VOICE_ROOT, "python")
    say(f"  no system Python with venv: downloading the standalone CPython {STANDALONE_VERSION} (about 50 MB, "
        f"hash checked)")
    return fetch_standalone(py)


def fetch_standalone(py: str) -> tuple[str, str]:
    """python-build-standalone's CPython into VOICE_ROOT/python: downloaded into a file of this run's own, hashed as
    it lies on disk, unpacked into a folder of this run's own, tried, then put in place with one rename -- another
    run at the same time (two bats at once) can never hand this one a half-written file."""
    import tarfile  # noqa: PLC0415
    os.makedirs(VOICE_ROOT, exist_ok=True)
    dest = os.path.dirname(os.path.dirname(py))
    fd, tmp = tempfile.mkstemp(prefix=".python-", suffix=".tar.gz.part", dir=VOICE_ROOT)
    unpack = None
    t0 = time.time()
    try:
        req = urllib.request.Request(STANDALONE_URL, headers={"User-Agent": "capri-kit"})
        got = 0
        with urllib.request.urlopen(req, timeout=300) as r, os.fdopen(fd, "wb") as f:
            expect = int(r.headers.get("Content-Length") or 0)
            for chunk in iter(lambda: r.read(1 << 20), b""):
                f.write(chunk)
                got += len(chunk)
        if expect and got != expect:
            raise Failed(f"the standalone Python's download stopped at {got} of {expect} bytes: run this again")
        digest = sha256_file(tmp)
        if digest != STANDALONE_SHA:
            raise Failed(f"the standalone Python downloaded ({got} B, sha256 {digest[:16]}...) does not hash as "
                         f"python-build-standalone publishes it ({STANDALONE_SHA[:16]}...)")
        say(f"    downloaded: {got} B in {time.time() - t0:.1f} s, sha256 {digest[:16]}... as published")
        unpack = tempfile.mkdtemp(prefix=".python-", dir=VOICE_ROOT)
        with tarfile.open(tmp, "r:gz") as t:
            members = t.getmembers()
            for m in members:
                if m.name.startswith("/") or ".." in m.name.split("/") or not m.name.startswith("python/"):
                    raise Failed(f"the standalone Python's archive has {m.name!r}")
            if hasattr(tarfile, "data_filter"):
                t.extractall(unpack, filter="data")
            else:
                t.extractall(unpack)  # noqa: S202 -- names checked above
        mine = os.path.join(unpack, "python", "bin", "python3")
        code, out = run([mine, "-c", "import sys, ensurepip, venv; print('%d.%d.%d' % sys.version_info[:3])"],
                        timeout=60)
        ver = out.strip().splitlines()[-1] if out.strip() else ""
        if code != 0 or ver != STANDALONE_VERSION:
            raise Failed(f"the standalone Python unpacked does not run as {STANDALONE_VERSION} with venv "
                         f"(exit {code}: {out.strip()[-200:]})")
        say(f"    unpacked ({len(members)} files) and tried: Python {ver} with venv and ensurepip")
        if os.path.isfile(py):
            say(f"    (another run of this kit put one in {dest} meanwhile: that one is used)")
            return py, f"the standalone CPython {STANDALONE_VERSION} kept in {dest}"
        if os.path.lexists(dest):
            aside = dest + ".unfinished-" + time.strftime("%Y%m%d-%H%M%S")
            os.rename(dest, aside)
            say(f"    an unfinished {dest} (a run that stopped halfway) moved aside: {aside}")
        try:
            os.rename(os.path.join(unpack, "python"), dest)
        except OSError:
            if not os.path.isfile(py):
                raise
            say(f"    (another run of this kit put one in {dest} meanwhile: that one is used)")
        return py, f"the standalone CPython {STANDALONE_VERSION}, just downloaded (hash checked)"
    finally:
        for path in (tmp,):
            try:
                os.remove(path)
            except OSError:
                pass
        if unpack:
            shutil.rmtree(unpack, ignore_errors=True)


def voice_versions(venv_py: str) -> dict:
    code, out = run([venv_py, "-c", "import importlib.metadata as m\nfor p in ('pocket-tts','torch','numpy'):\n"
                     "    try: print(p, m.version(p))\n    except Exception: print(p, '-')"], timeout=120)
    got = dict(l.split(" ", 1) for l in out.strip().splitlines() if " " in l) if code == 0 else {}
    return got


def voices_from_package(role: str) -> dict:
    """Her voice states (voces/capri_<language>.safetensors) from ROLE's live Capri package, into VOICE_ROOT/voces:
    the very files every player's Capri Voz has. {file: sha256}."""
    name, world, root = role_paths(role)
    text, cfg = load_cfg(root)
    entry = capri_entry(cfg)
    if entry is None:
        raise Failed(f"{world} has no {MOD_ID} entry")
    blob = os.path.join(mods_dir(root, cfg), f"{entry.get('sha256')}.blob")
    if not os.path.isfile(blob) or sha256_file(blob) != entry.get("sha256"):
        raise Failed(f"{world}: the live Capri blob is not in the hosted store, or hashes otherwise")
    out = {}
    dest = os.path.join(VOICE_ROOT, "voces")
    os.makedirs(dest, exist_ok=True)
    os.chmod(dest, 0o755)
    with zipfile.ZipFile(blob) as z:
        for info in z.infolist():
            n = info.filename.replace("\\", "/")
            m = re.match(re.escape(VOICE_FILES) + r"(capri_[a-z]+\.safetensors)$", n)
            if not m:
                continue
            data = z.read(info)
            path = os.path.join(dest, m.group(1))
            if not os.path.isfile(path) or sha256_file(path) != hashlib.sha256(data).hexdigest():
                with open(path + ".tmp", "wb") as f:
                    f.write(data)
                os.chmod(path + ".tmp", 0o644)
                os.replace(path + ".tmp", path)
            out[m.group(1)] = hashlib.sha256(data).hexdigest()
    if not out:
        raise Failed(f"{world}'s Capri package has no voice state of hers (voces/capri_<language>.safetensors)")
    return out


SANDBOX_LINES = ("NoNewPrivileges=yes", "PrivateTmp=yes", "ProtectSystem=strict", "ReadWritePaths=", "ProtectHome=yes",
                 "ProtectKernelTunables=yes", "ProtectKernelModules=yes", "ProtectControlGroups=yes",
                 "RestrictNamespaces=yes", "LockPersonality=yes")


def voice_unit_text(threads: int, sandbox: bool = True) -> str:
    """Its unit; sandbox=False leaves out the options that need mount namespaces (a container that refuses them
    fails the unit with 226/NAMESPACE) -- it still runs as its own user, with no login."""
    text = _voice_unit_text(threads)
    if sandbox:
        return text
    return "".join(l for l in text.splitlines(True) if not l.startswith(SANDBOX_LINES))


def _voice_unit_text(threads: int) -> str:
    return f"""[Unit]
Description=Capri's voice for XyberRP players (Pocket TTS with her own voice states; the XyberRP Capri kit)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={VOICE_USER}
Group={VOICE_USER}
WorkingDirectory={VOICE_ROOT}
ExecStart={VOICE_ROOT}/venv/bin/python -u {VOICE_ROOT}/capri_voice_server.py --host 127.0.0.1 --port {VOICE_PORT} --voices {VOICE_ROOT}/voces --threads {threads}
Environment=HF_HOME={VOICE_ROOT}/hf
Environment=HF_HUB_OFFLINE=1
Environment=HF_HUB_DISABLE_XET=1
Environment=HF_HUB_DISABLE_TELEMETRY=1
Environment=HOME=/tmp
Environment=PYTHONUNBUFFERED=1
Nice=5
CPUWeight=50
MemoryMax=3G
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths={VOICE_ROOT}/hf
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictNamespaces=yes
LockPersonality=yes
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def voice_location_text(indent: str, secret: str) -> str:
    i2 = indent + "    "
    return (f"{indent}{VOICE_MARK} (its private path travels in the Capri package to every player)\n"
            f"{indent}location /{secret}/ {{\n"
            f"{i2}limit_req zone=capri_voice burst={VOICE_BURST} nodelay;\n"
            f"{i2}limit_req_status 429;\n"
            f"{i2}client_max_body_size 32k;\n"
            f"{i2}proxy_pass http://127.0.0.1:{VOICE_PORT}/;\n"
            f"{i2}proxy_set_header X-Real-IP $remote_addr;\n"
            f"{i2}proxy_read_timeout 90s;\n"
            f"{i2}proxy_buffering off;\n"
            f"{indent}}}\n")


VOICE_ZONE = (f"{VOICE_MARK}: the limit per address\n"
              f"limit_req_zone $binary_remote_addr zone=capri_voice:1m rate={VOICE_RATE};\n")


def voice_nginx(cur: dict, secret: str) -> str:
    """nginx serves her voice under /SECRET/ in the brain's server block (kept first, nginx -t, reload, asked through
    nginx; put back on any failure). Returns what happened."""
    if any(l["path"].rstrip("/") == "/" + secret and l["host"] == cur["host"] for l in voice_locations()):
        return "already served"
    conf = cur.get("file")
    if not conf or not os.path.isfile(conf):
        raise Failed("nginx -T does not say which file holds the brain's location")
    real = os.path.realpath(conf)
    text = open(real, encoding="utf-8").read()
    hits = list(location_rx(cur["path"], cur["modifier"]).finditer(text))
    if len(hits) != 1:
        raise Failed(f"{real}: the brain's location is there {len(hits)} times (one expected): her voice's location "
                     f"cannot be put next to it")
    m = hits[0]
    new = text[:m.start()] + voice_location_text(m.group(1), secret) + text[m.start():]
    code, all_conf = run(NGINX + ["-T"], timeout=30)
    if not re.search(r"^\s*limit_req_zone\s.*zone=capri_voice:", all_conf, re.M):
        new = VOICE_ZONE + "\n" + new
    backup = keep_site(real, "voice")
    write_site(real, new)
    say(f"{real}: her voice's location added next to the brain's (limit_req {VOICE_RATE} burst {VOICE_BURST}, 429; "
        f"-> 127.0.0.1:{VOICE_PORT}); kept first: {backup}")

    def put_back(why):
        shutil.copy2(backup, real)
        c1, o1 = run(NGINX + ["-t"], timeout=30)
        c2, o2 = nginx_reload() if c1 == 0 else (c1, o1)
        raise Failed(f"{why}: {real} PUT BACK (nginx -t {'ok' if c1 == 0 else 'FAILED'}, reload exit {c2})")
    code, out = run(NGINX + ["-t"], timeout=30)
    if code != 0:
        say("  " + "\n  ".join(out.strip().splitlines()[-4:]))
        put_back("nginx -t refused it")
    code, out = nginx_reload()
    if code != 0:
        put_back(f"nginx did not reload ({out.strip()[-200:]})")
    st, body, took = through_nginx(cur["host"], "/" + secret + "/health", timeout=20)
    if st != 200 or not isinstance(body, dict) or body.get("service") != "capri-voice":
        put_back(f"her voice does not answer through nginx after it ({st or 'no answer'})")
    try:
        cur2 = brain()
    except Failed as e:
        put_back(f"the brain does not answer through nginx after it ({e})")
    rec = voice_record()
    rec.setdefault("nginx", []).append({"at": time.strftime("%Y%m%d-%H%M%S", time.gmtime()), "file": real,
                                        "backup": backup})
    save_voice_record(rec)
    return f"added; asked through nginx: /health -> 200 in {took:.2f} s, the brain still answers ({cur2['seconds']} s)"


def cmd_voice(a) -> int:
    """Capri's own voice for every player: the same engine and voice states a player's local engine runs, here."""
    facts = machine_facts()
    say(f"this machine: {facts.get('os', '?')}, {facts.get('cpus')} CPU(s) (load {facts.get('load', '?')}), memory "
        f"{facts.get('available_gb')} of {facts.get('memory_gb')} GB free, {facts.get('disk_free_gb')} GB free on disk")
    cur = brain()
    rec = voice_record()
    role = a.role or "staging"
    server_src = os.path.join(a.work, "capri_voice_server.py")
    if not os.path.isfile(server_src):
        raise Failed("capri_voice_server.py was not sent along")
    server_sha = sha256_file(server_src)
    threads = max(2, min(4, (os.cpu_count() or 4) // 4))
    unit_path = os.path.join(VOICE_UNIT_DIR, VOICE_UNIT + ".service")
    venv_py = os.path.join(VOICE_ROOT, "venv", "bin", "python")
    # 1. her voice states, from the live package
    voices = voices_from_package(role)
    say(f"her voice states, from {ROLES[role][1]}'s live Capri package: " +
        ", ".join(f"{k} ({v[:12]}...)" for k, v in sorted(voices.items())))
    # nothing to do when it is all there, answering, and as this kit would make it
    health = voice_local_health()
    have = voice_versions(venv_py) if os.path.isfile(venv_py) else {}
    unit_now = open(unit_path, encoding="utf-8").read() if os.path.isfile(unit_path) else ""
    unit_same = unit_now in (voice_unit_text(threads), voice_unit_text(threads, sandbox=False))
    installed_same = (os.path.isfile(os.path.join(VOICE_ROOT, "capri_voice_server.py")) and
                      sha256_file(os.path.join(VOICE_ROOT, "capri_voice_server.py")) == server_sha)
    langs_ok = isinstance(health, dict) and all((health.get("languages") or {}).get(c, {}).get("voice") == "capri"
                                                for c in ("en", "es"))
    if (have.get("pocket-tts") == POCKET_PIN and have.get("torch", "").startswith(TORCH_PIN) and unit_same
            and installed_same and langs_ok and rec.get("voices") == voices and rec.get("secret")):
        say(f"her voice is installed as this kit makes it and answers here (Pocket TTS {have.get('pocket-tts')}, "
            f"torch {have.get('torch')}; {', '.join(sorted(health.get('languages') or {}))} with her own voice; "
            f"{health.get('spoken')} line(s) said since its start)")
        how = voice_nginx(cur, rec["secret"])
        now = voice_now(cur["host"])
        if not now.get("url"):
            raise Failed(f"her voice does not reach players: {now.get('why')}")
        say(f"through nginx: {how}; {now['languages']} answered in {now['seconds']} s")
        fd = os.open(os.path.join(a.work, "voice.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(now["url"] + "\n")
        result(command="voice", changed=False, why="already", languages=now["languages"], threads=threads,
               versions=have)
        return NO
    if a.check_only:
        why = []
        if have.get("pocket-tts") != POCKET_PIN:
            why.append(f"Pocket TTS {have.get('pocket-tts') or 'not installed'}")
        if not unit_same:
            why.append("its unit is not as this kit writes it")
        if not installed_same:
            why.append("its program is not this kit's")
        if not langs_ok:
            why.append("it does not answer with her voice in English and Spanish")
        say("her voice is not (all) there: " + "; ".join(why))
        result(command="voice", changed=False, why="check only", missing=why)
        return 1
    if (facts.get("disk_free_gb") or 99) < 3:
        raise Failed(f"only {facts.get('disk_free_gb')} GB free on disk: her voice needs about 2.5 GB")
    # her two models take about 1.5 GB once loaded: with less free, the game servers would be the ones to suffer
    if (facts.get("available_gb") or 99) < 2.0:
        raise Failed(f"only {facts.get('available_gb')} GB of memory free: her voice needs about 1.5 GB -- nothing "
                     f"installed, so the game servers keep theirs")
    # 2. a Python and her engine
    os.makedirs(VOICE_ROOT, exist_ok=True)
    os.chmod(VOICE_ROOT, 0o755)
    if not (have.get("pocket-tts") == POCKET_PIN and have.get("torch", "").startswith(TORCH_PIN)):
        if not os.path.isfile(venv_py):
            py, how = pick_python()
            say(f"a Python for her engine: {how}")
            code, out = run([py, "-m", "venv", os.path.join(VOICE_ROOT, "venv")], timeout=300)
            if code != 0 or not os.path.isfile(venv_py):
                raise Failed("the venv could not be made: " + out.strip()[-300:])
            say(f"venv made: {os.path.join(VOICE_ROOT, 'venv')}")
        t0 = time.time()
        say(f"installing PyTorch {TORCH_PIN} for the CPU (about 200 MB)...")
        code, out = run([venv_py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-q",
                         f"torch=={TORCH_PIN}", "--index-url", TORCH_INDEX], timeout=2400)
        if code != 0:
            raise Failed("pip could not install PyTorch: " + " | ".join(out.strip().splitlines()[-4:]))
        say(f"installing Pocket TTS {POCKET_PIN}... ({time.time() - t0:.0f} s so far)")
        code, out = run([venv_py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-q",
                         f"pocket-tts=={POCKET_PIN}", "--extra-index-url", TORCH_INDEX], timeout=2400)
        if code != 0:
            raise Failed("pip could not install Pocket TTS: " + " | ".join(out.strip().splitlines()[-4:]))
        have = voice_versions(venv_py)
        say(f"installed in {time.time() - t0:.0f} s: Pocket TTS {have.get('pocket-tts')}, torch {have.get('torch')}, "
            f"numpy {have.get('numpy')}")
        if have.get("pocket-tts") != POCKET_PIN or not have.get("torch", "").startswith(TORCH_PIN):
            raise Failed(f"the venv holds Pocket TTS {have.get('pocket-tts')} and torch {have.get('torch')}, not "
                         f"{POCKET_PIN} and {TORCH_PIN}")
    else:
        say(f"her engine is installed already: Pocket TTS {have.get('pocket-tts')}, torch {have.get('torch')}")
    # 3. the program, and the self-test (it downloads her models into VOICE_ROOT/hf the first time)
    shutil.copyfile(server_src, os.path.join(VOICE_ROOT, "capri_voice_server.py"))
    os.chmod(os.path.join(VOICE_ROOT, "capri_voice_server.py"), 0o644)
    hf = os.path.join(VOICE_ROOT, "hf")
    os.makedirs(hf, exist_ok=True)
    env = dict(os.environ, HF_HOME=hf, HF_HUB_DISABLE_XET="1", HF_HUB_DISABLE_TELEMETRY="1", PYTHONIOENCODING="utf-8")
    say(f"self-test: her models (downloaded the first time, about 450 MB) and one line in each language, on "
        f"{threads} thread(s)...")
    t0 = time.time()
    code, out = run([venv_py, os.path.join(VOICE_ROOT, "capri_voice_server.py"), "--voices",
                     os.path.join(VOICE_ROOT, "voces"), "--selftest", os.path.join(VOICE_ROOT, "selftest"),
                     "--threads", str(threads)], timeout=2400, env=env)
    test = {}
    for line in out.splitlines():
        if line.startswith("{") and '"languages"' in line:
            try:
                test = json.loads(line)
            except ValueError:
                pass
    for lang, r in sorted((test.get("languages") or {}).items()):
        say(f"  {lang}: voice {r.get('voice')}, {r.get('seconds')} s of audio in {r.get('gen_s')} s (load "
            f"{r.get('load_s')} s), RMS {r.get('rms')}, {'ok' if r.get('ok') else '!! ' + str(r.get('why'))}")
    if code != 0 or not test.get("ok"):
        tail = [l for l in out.strip().splitlines() if not l.startswith("{")][-6:]
        for l in tail:
            say("  " + l[:300])
        raise Failed(f"the self-test failed (exit {code}): her voice is not installed for players")
    say(f"self-test passed in {time.time() - t0:.0f} s (Pocket TTS {test.get('pocket_tts')}, torch {test.get('torch')})")
    # 4. its user and its unit
    code, out = run(["id", "-u", VOICE_USER], timeout=20)
    if code != 0:
        code, out = run(["useradd", "--system", "--no-create-home", "--home-dir", VOICE_ROOT, "--shell",
                         "/usr/sbin/nologin", VOICE_USER], timeout=60)
        if code != 0:
            raise Failed(f"the system user {VOICE_USER} could not be made: {out.strip()[-200:]}")
        say(f"system user {VOICE_USER} made (no login, no home of its own)")
    code, out = run(["chown", "-R", f"{VOICE_USER}:{VOICE_USER}", hf], timeout=300)
    if code != 0:
        raise Failed(f"{hf} could not be given to {VOICE_USER}: {out.strip()[-200:]}")
    def start(sandbox: bool):
        unit_text = voice_unit_text(threads, sandbox)
        if not os.path.isfile(unit_path) or open(unit_path, encoding="utf-8").read() != unit_text:
            with open(unit_path + ".tmp", "w", encoding="utf-8") as f:
                f.write(unit_text)
            os.replace(unit_path + ".tmp", unit_path)
            say(f"{unit_path} written ({threads} thread(s), Nice 5, at most 3 GB, "
                + ("read-only but for its model cache)" if sandbox else "without the sandbox options this machine refuses)"))
        run(SYSTEMCTL + ["daemon-reload"], timeout=60)
        run(SYSTEMCTL + ["enable", VOICE_UNIT], timeout=60)
        code, out = run(SYSTEMCTL + ["restart", VOICE_UNIT], timeout=120)
        t0 = time.time()
        health = None
        while time.time() - t0 < 240:
            health = voice_local_health()
            if isinstance(health, dict) and all((health.get("languages") or {}).get(c, {}).get("voice") == "capri"
                                                for c in ("en", "es")):
                return health, t0
            state = unit_state(VOICE_UNIT + ".service")
            if state in ("failed", "inactive") and time.time() - t0 > 6:
                break
            time.sleep(2)
        code, j = run(["journalctl", "-u", VOICE_UNIT, "-n", "20", "--no-pager", "-o", "cat"], timeout=30)
        for l in j.strip().splitlines()[-12:]:
            say("  journal: " + l[:240])
        code, show = run(SYSTEMCTL + ["show", VOICE_UNIT, "-p", "ActiveState,Result,ExecMainStatus"], timeout=20)
        say("  " + " ".join(show.split()))
        return None, t0
    health, t0 = start(True)
    if health is None and unit_state(VOICE_UNIT + ".service") in ("failed", "inactive", "activating"):
        say(f"{VOICE_UNIT} did not come up with its sandbox options (a container that refuses mount namespaces "
            f"fails it with 226/NAMESPACE): once more without them")
        health, t0 = start(False)
    if health is None:
        raise Failed(f"{VOICE_UNIT} does not answer with her voice in English and Spanish: see its journal lines above")
    say(f"{VOICE_UNIT}: active, answers on 127.0.0.1:{VOICE_PORT} with her own voice in "
        f"{', '.join(sorted(health.get('languages') or {}))} ({time.time() - t0:.0f} s to load)")
    # 5. nginx: her own private path, limited per address
    secret = rec.get("secret") or ("capri-voice-" + hashlib.sha256(os.urandom(32)).hexdigest()[:24])
    rec.update(secret=secret, host=cur["host"])
    save_voice_record(rec)
    how = voice_nginx(cur, secret)
    now = voice_now(cur["host"])
    if not now.get("url"):
        raise Failed(f"her voice does not reach players: {now.get('why')}")
    say(f"through nginx ({cur['host']}/capri-voice-<secret>/): {how}")
    rec = voice_record()
    rec.update(voices=voices, versions=have, server_sha=server_sha, threads=threads,
               at=time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    save_voice_record(rec)
    fd = os.open(os.path.join(a.work, "voice.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(now["url"] + "\n")
    result(command="voice", changed=True, languages=now["languages"], threads=threads, versions=have)
    return 0


# ------------------------------------------------------------------------------------------------ the gates
def gate_paths(role: str) -> tuple[str, str, int, str]:
    folder, unit, port, public = GATES[role]
    return os.path.join(SERVERS_ROOT, folder), unit, port, public


def gate_ask(port: int, path: str, timeout=5) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, e.__class__.__name__


def through_nginx_text(host: str, path: str, timeout=20) -> tuple[int, str]:
    code, out = run(CURL + ["-sS", "--max-time", str(timeout), "--resolve", f"{host}:443:127.0.0.1",
                            "-w", "\n%{http_code}", f"https://{host}{path}"], timeout=timeout + 5)
    body, _, status = out.rpartition("\n")
    try:
        return int(status.strip()), body
    except ValueError:
        return 0, out[-200:]


def gate_state(role: str) -> dict:
    folder, unit, port, public = gate_paths(role)
    st, text = gate_ask(port, "/state")
    try:
        return json.loads(text) if st == 200 else {}
    except ValueError:
        return {}


def cmd_gate(a) -> int:
    """ROLE's Mass Override gate updated to the kit's gate.js and dev-server.js: every game polls GET /casts and
    runs everyone's casts.  Older game builds keep working (/feed, /players, /cast without a session)."""
    folder, unit, port, public = gate_paths(a.role)
    world = ROLES[a.role][1]
    new = {n: open(os.path.join(a.work, n), "rb").read() for n in ("gate.js", "dev-server.js")
           if os.path.isfile(os.path.join(a.work, n))}
    if len(new) != 2:
        raise Failed("gate.js and dev-server.js were not sent along")
    if b"GET /casts" not in new["dev-server.js"]:
        raise Failed("the dev-server.js sent along is not the one that hands out casts (GET /casts)")
    if not os.path.isdir(folder):
        raise Failed(f"{world}'s gate is not on this machine ({folder}): set it up first (mo-gate-prod.sh)")
    old = {n: open(os.path.join(folder, n), "rb").read() if os.path.isfile(os.path.join(folder, n)) else b""
           for n in new}
    cur = brain()
    if old == new and unit_state(unit + ".service") == "active":
        st, text = gate_ask(port, "/casts?since=0&session=capri-kit")
        nst, ntext = through_nginx_text(cur["host"], public + "casts?since=0&session=capri-kit")
        say(f"{world}'s gate ({unit}) is this kit's already and active: /casts -> {st} here, {nst} through nginx")
        result(command="gate", role=a.role, changed=False, why="already", local=st, nginx=nst)
        return NO if st == 200 and nst == 200 else 1
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    keep = os.path.join(STATE_DIR, "gate", f"{a.role}-{ts}")
    os.makedirs(keep, mode=0o700, exist_ok=True)
    for n, b in old.items():
        with open(os.path.join(keep, n), "wb") as f:
            f.write(b)
    before = gate_state(a.role)
    for n, b in new.items():
        tmp = os.path.join(folder, n + ".capri-kit.tmp")
        with open(tmp, "wb") as f:
            f.write(b)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(folder, n))
    say(f"{world}'s gate: gate.js and dev-server.js replaced ({', '.join(f'{n} {hashlib.sha256(b).hexdigest()[:12]}' for n, b in new.items())}); "
        f"the old ones kept in {keep}")

    def put_back(why):
        for n, b in old.items():
            with open(os.path.join(folder, n), "wb") as f:
                f.write(b)
        c, o = run(SYSTEMCTL + ["restart", unit], timeout=60)
        raise Failed(f"{why}: the old gate PUT BACK and restarted (exit {c})")
    code, out = run(SYSTEMCTL + ["restart", unit], timeout=60)
    if code != 0:
        put_back(f"{unit} did not restart ({out.strip()[-200:]})")
    t0 = time.time()
    st, text = 0, ""
    while time.time() - t0 < 30:
        st, text = gate_ask(port, "/casts?since=0&session=capri-kit")
        if st == 200:
            break
        time.sleep(1)
    lines = text.splitlines()
    if st != 200 or not lines or not re.match(r"^\d+$", lines[0]):
        put_back(f"the new gate does not answer GET /casts here ({st} {text[:80]!r})")
    fst, ftext = gate_ask(port, "/feed?since=0")
    if fst != 200 or not re.match(r"^\d+ \w+$", ftext.strip()):
        put_back(f"the new gate does not answer the older builds' GET /feed ({fst} {ftext[:80]!r})")
    nst, ntext = through_nginx_text(cur["host"], public + "casts?since=0&session=capri-kit")
    if nst != 200:
        put_back(f"the new gate does not answer through nginx ({public}casts -> {nst})")
    after = gate_state(a.role)
    say(f"{world}'s gate restarted: GET /casts -> 200 here and through nginx ({cur['host']}{public}casts), GET /feed "
        f"still answers the older builds ({ftext.strip()}); casts it remembers: {len((after or {}).get('recent') or [])}"
        f" (the restart forgets the ones before it: {len((before or {}).get('recent') or []) if before else '?'})")
    result(command="gate", role=a.role, changed=True, kept=keep)
    return 0



# ------------------------------------------------------------------------------------------------ the brain's program
# capri-brain.mjs as this kit's earlier builds left it (sha256): a file that is one of these is replaced whole; any
# other is changed in its Mass Override line only, or not at all.
BRAIN_KNOWN = {
    "07774166e7bdc43f78690f4085f16ea7c8a79ce5055cf1f53c0b453003322ef9": "982374d (2026-11-11, the Mass Override shortcut)",
}
BRAIN_OLD_RX = ("const MASS_OVERRIDE_REQUEST =\n  /change everything around me|mass[\\s-]*override|everything around me[^.!?]*"
                "(lights|screens|cars)|(lights|screens|cars)[^.!?]*(go out|turn hostile)/i;\n")
BRAIN_ASK_SYSTEM = 'Capri kit check.\n {"do":"mass_override","target":...} change everything around V at once\n'
BRAIN_ASKS = ("mass over ride", "MASS OVERRIDE")


def brain_script(pid: int) -> tuple[str, str]:
    """(capri-brain.mjs, node) of the process behind the brain's port: its command line, read from /proc."""
    try:
        argv = [x.decode("utf-8", errors="replace") for x in open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0") if x]
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError as e:
        raise Failed(f"the brain's process ({pid}) cannot be read: {e}") from e
    script = next((x for x in argv[1:] if x.endswith(".mjs") or x.endswith(".js")), "")
    if not script:
        raise Failed(f"the brain's process runs no .mjs file: {clean(' '.join(argv)[:160])}")
    script = os.path.realpath(os.path.join(cwd, script))
    node = argv[0] if os.path.isabs(argv[0]) else (shutil.which(argv[0]) or "")
    if not node:
        try:
            node = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            node = shutil.which("node") or "node"
    return script, node


def brain_mo_block(new: str) -> str:
    """The new file's Mass Override recognizer: from its MASS_OVERRIDE_WORDS line to the end of MASS_OVERRIDE_REQUEST."""
    m = re.search(r"^const MASS_OVERRIDE_WORDS = .*?^\);\n", new, re.S | re.M)
    if not m or "const MASS_OVERRIDE_REQUEST = new RegExp(" not in m.group(0):
        raise Failed("the capri-brain.mjs sent along has no Mass Override recognizer this kit can carry over")
    return m.group(0)


def brain_post(port: int, said: str, timeout=10) -> tuple[int, dict, float]:
    """One chat request to the brain on this machine, the way a game with Mass Override sends one: (status, reply)."""
    body = json.dumps({"model": "capri-brain", "max_tokens": 32, "messages": [
        {"role": "system", "content": BRAIN_ASK_SYSTEM}, {"role": "user", "content": said}]}).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            st = r.status
    except urllib.error.HTTPError as e:
        return e.code, {}, time.time() - t0
    except (urllib.error.URLError, OSError, ValueError):
        return 0, {}, time.time() - t0
    try:
        reply = json.loads(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}")
    except ValueError:
        reply = {}
    return st, reply if isinstance(reply, dict) else {}, time.time() - t0


def brain_hears(port: int) -> list[str]:
    """Each of BRAIN_ASKS to the brain here: what is wrong ([] when every one comes back as a cast at once)."""
    wrong = []
    for said in BRAIN_ASKS:
        st, reply, took = brain_post(port, said)
        acts = [x.get("do") for x in reply.get("actions") or [] if isinstance(x, dict)]
        ok = st == 200 and "mass_override" in acts and took < 5
        say(f"  {said!r} -> {st or 'no answer'} in {took:.2f} s: " + (f"actions {acts}, {reply.get('say')!r}" if st == 200
                                                                     else "no reply") + ("" if ok else "  !! not a cast"))
        if not ok:
            wrong.append(said)
    return wrong


def brain_restarted(unit: str, port: int, since: float, want_build: str | None, wait=45) -> dict:
    """The unit restarted, then its health on the brain's port from a process that started after SINCE."""
    code, out = run(SYSTEMCTL + ["restart", unit], timeout=60)
    if code != 0:
        raise Failed(f"systemctl restart {unit}: exit {code}: {out.strip()[-200:]}")
    t0 = time.time()
    last = None
    while time.time() - t0 < wait:
        try:
            h = http_json(f"http://127.0.0.1:{port}/health", timeout=3)
            fresh = isinstance(h.get("uptimeSeconds"), (int, float)) and h["uptimeSeconds"] <= time.time() - since + 2
            if fresh and (not want_build or h.get("build") == want_build):
                return h
            last = f"up {h.get('uptimeSeconds')} s, build {h.get('build')}"
        except Exception as e:  # noqa: BLE001
            last = e.__class__.__name__
        time.sleep(1)
    raise Failed(f"the brain did not come back on 127.0.0.1:{port} in {wait} s after its restart (last: {last})")


def gate_lines(role: str, n=8) -> list[str]:
    """(read only) ROLE's gate's last casts, refusals and reports, as its journal has them."""
    folder, unit, port, public = gate_paths(role)
    code, out = run(["journalctl", "-u", unit, "-n", "400", "--no-pager", "-o", "short-iso"], timeout=20)
    return [l for l in out.splitlines() if "[cast]" in l or "[report]" in l][-n:]


def net_facts() -> list[str]:
    """(read only) What on this machine could drop or refuse a player's connection: firewall rules that limit new
    connections per address, the kernel's dropped connection attempts, the connection table, nginx's own limits hit
    lately.  On 2026-11-12 one PC's requests failed now and then ("Failed to connect ... after 21025 ms", "Connection
    was reset") while the other's went through."""
    out = []
    code, o = run(["ufw", "status", "verbose"], timeout=15)
    if code == 0 and o.strip():
        lim = [l.strip() for l in o.splitlines() if " LIMIT " in f" {l.upper()} "]
        out.append(f"ufw: {o.splitlines()[0].strip()}; rules that LIMIT new connections: {len(lim)}"
                   + (" -- " + " | ".join(lim[:6]) if lim else ""))
    code, o = run(["iptables", "-S"], timeout=15)
    if code == 0:
        lim = [l.strip() for l in o.splitlines() if re.search(r"--limit|-m recent|hashlimit|connlimit", l)]
        out.append(f"iptables: {len(o.splitlines())} rule(s), {len(lim)} limiting" + (" -- " + " | ".join(lim[:6]) if lim else ""))
    code, o = run(["nft", "list", "ruleset"], timeout=15)
    if code == 0:
        lim = [l.strip() for l in o.splitlines() if re.search(r"\blimit rate\b|\bmeter\b|ct count|\bquota\b", l)]
        out.append(f"nft: {len(o.splitlines())} line(s), {len(lim)} limiting" + (" -- " + " | ".join(lim[:6]) if lim else ""))
    code, o = run(["nstat", "-az", "TcpExtListenDrops", "TcpExtListenOverflows", "TcpExtTCPReqQFullDrop",
                   "TcpExtSyncookiesSent", "TcpExtTCPAbortOnData"], timeout=10)
    if code == 0:
        vals = {m.group(1): m.group(2) for m in re.finditer(r"^(\w+)\s+(\d+)", o, re.M)}
        out.append("kernel since boot: " + ", ".join(f"{k.replace('TcpExt', '')} {v}" for k, v in vals.items()))
    try:
        cnt = open("/proc/sys/net/netfilter/nf_conntrack_count").read().strip()
        mx = open("/proc/sys/net/netfilter/nf_conntrack_max").read().strip()
        out.append(f"connection table: {cnt} of {mx}")
    except OSError:
        pass
    hits = {}
    for path in ("/var/log/nginx/error.log",):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-5000:]
        except OSError:
            continue
        for l in tail:
            m = re.search(r"limiting (requests|connections)[^,]*, excess[^,]*, by zone \"([^\"]+)\"|limiting (connections) by zone \"([^\"]+)\"", l)
            if m:
                key = (m.group(1) or m.group(3)) + " " + (m.group(2) or m.group(4))
                hits[key] = hits.get(key, 0) + 1
        out.append("nginx limits hit (its error log's last 5000 lines): " + (", ".join(f"{k} x{v}" for k, v in hits.items())
                                                                              or "none"))
    return out


def cmd_brain(a) -> int:
    """The brain's program updated to the kit's capri-brain.mjs: Mass Override however a player types it ("mass over
    ride" went to the model, which answered with banter).  Kept first, checked by node, the unit restarted, asked here;
    put back on any failure."""
    sent = os.path.join(a.work, "capri-brain.mjs")
    if not os.path.isfile(sent):
        raise Failed("capri-brain.mjs was not sent along")
    new = open(sent, encoding="utf-8").read()
    build = re.search(r"^const BRAIN_BUILD = '([^']+)';", new, re.M)
    if not build or "MASS_OVERRIDE_WORDS" not in new:
        raise Failed("the capri-brain.mjs sent along is not the one that hears Mass Override however it is typed")
    build = build.group(1)
    block = brain_mo_block(new)
    b = brain()
    u = brain_unit(b["proxy_pass"])
    port, pid = u.get("port"), u.get("pid")
    unit = os.environ.get("CAPRI_BRAIN_UNIT") or u.get("unit")
    say(f"the brain: {b['host']}{clean(b['base'])} -> 127.0.0.1:{port}, unit {unit or '?'} ({u.get('state', '?')}), "
        f"pid {pid or '?'}")
    say("its last requests (how each went; never what was said):")
    for l in u.get("chats") or ["(none in its journal)"]:
        say("  " + l[:220])
    for role in ("production", "staging"):
        lines = gate_lines(role)
        if lines:
            say(f"(read only) {ROLES[role][1]}'s gate lately:")
            for l in lines:
                say("  " + l[:260])
    say("(read only) what on this machine could drop a player's connection:")
    for l in net_facts() or ["(nothing could be read)"]:
        say("  " + l[:400])
    if not port or not pid:
        raise Failed("no process listens on the brain's port: nothing changed")
    if not unit:
        raise Failed("the unit behind the brain's port is not known (its process is not in a .service): nothing changed")
    script, node = brain_script(pid)
    cur = open(script, encoding="utf-8").read()
    cur_sha = hashlib.sha256(cur.encode("utf-8")).hexdigest()
    say(f"its program: {script} ({len(cur)} B, sha256 {cur_sha[:16]}...), run by {node}")
    health = u.get("health") if isinstance(u.get("health"), dict) else {}
    if cur == new:
        say(f"it is this kit's build already ({build}); running: {health.get('build') or '?'}")
        wrong = brain_hears(port)
        if not wrong and health.get("build") == build:
            fd = os.open(os.path.join(a.work, "brain.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(b["url"] + "\n")
            result(command="brain", changed=False, why="already", build=build)
            return NO
        say("  (the file is the new one but the brain running is not, or does not hear it: restarted below)")
        data, how = new, "the same file, restarted"
    elif cur_sha in BRAIN_KNOWN:
        data, how = new, f"replaced whole: it was this kit's earlier build {BRAIN_KNOWN[cur_sha]}"
    elif re.search(r"^const BRAIN_BUILD = '[^']+';", cur, re.M) and "MASS_OVERRIDE_WORDS" in cur:
        was = re.search(r"^const BRAIN_BUILD = '([^']+)';", cur, re.M).group(1)
        data, how = new, f"replaced whole: it was this kit's build {was}"
    elif cur.count(BRAIN_OLD_RX) == 1:
        data, how = cur.replace(BRAIN_OLD_RX, block), "its Mass Override recognizer replaced, the rest of it as it was"
        build = None
    else:
        raise Failed(f"{script} is not a brain this kit knows and has no Mass Override line it can replace: nothing "
                     f"changed (sha256 {cur_sha[:16]}..., {len(cur)} B)")
    st = os.stat(script)
    # next to it, and still a .mjs: node only checks an ES module by its extension
    tmp = os.path.join(os.path.dirname(script), ".capri-kit-new-" + os.path.basename(script))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.chmod(tmp, stat_mode(st))
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    code, out = run([node, "--check", tmp], timeout=60)
    if code != 0:
        os.remove(tmp)
        raise Failed(f"node does not accept the new program: nothing changed ({out.strip()[-300:]})")
    say(f"node --check: the new program is accepted ({len(data)} B)")
    keep = os.path.join(STATE_DIR, "brain")
    os.makedirs(keep, mode=0o700, exist_ok=True)
    kept = os.path.join(keep, f"capri-brain.mjs.before-capri-kit-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(script, kept)
    os.chmod(kept, 0o600)
    os.replace(tmp, script)
    say(f"{script}: {how}; kept first: {kept}")
    since = time.time()
    try:
        h = brain_restarted(unit, port, since, build)
        say(f"{unit} restarted: up again in {time.time() - since:.1f} s, build {h.get('build') or '(none: an older '
            f'brain with the new recognizer)'}, backend {h.get('backend')} {'answers' if h.get('backendOk') else 'does NOT answer'}")
        say("asked here, the way a game with Mass Override asks it:")
        wrong = brain_hears(port)
        if wrong:
            raise Failed("it still does not cast for: " + ", ".join(repr(w) for w in wrong))
        again = brain()
        say(f"through nginx: v1/models -> 200 ({', '.join(again.get('models') or [])})")
    except Failed as e:
        say(f"!! {e} -- PUT BACK: the program as it was, and the unit restarted")
        shutil.copy2(kept, script)
        os.chmod(script, stat_mode(st))
        try:
            os.chown(script, st.st_uid, st.st_gid)
        except OSError:
            pass
        try:
            h = brain_restarted(unit, port, time.time(), None)
            say(f"put back: the brain answers again (up {h.get('uptimeSeconds')} s)")
        except Failed as e2:
            say(f"!! put back, but it does not answer yet: {e2}")
        raise Failed(f"the brain was put back as it was: {e}") from e
    code, j = run(["journalctl", "-u", unit, "-n", "40", "--no-pager", "-o", "short-iso"], timeout=20)
    for l in [l for l in j.splitlines() if "[capri-brain]" in l][-4:]:
        say("  journal: " + l[:220])
    fd = os.open(os.path.join(a.work, "brain.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(b["url"] + "\n")
    result(command="brain", changed=True, how=how, build=h.get("build"), kept=kept)
    return 0


def stat_mode(st) -> int:
    return st.st_mode & 0o7777


def dispatch(a) -> int:
    if a.command == "look":
        return cmd_look(a)
    if a.command == "guard":
        return cmd_guard(a)
    if a.command == "guard-putback":
        return cmd_guard_putback(a)
    if a.command == "voice":
        return cmd_voice(a)
    if a.command == "brain":
        return cmd_brain(a)
    if not a.role:
        raise Failed("--role staging or production")
    return {"fetch": cmd_fetch, "assemble": cmd_assemble, "import": cmd_import, "verify": cmd_verify,
            "putback": cmd_putback, "gate": cmd_gate}[a.command](a)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["look", "fetch", "assemble", "import", "verify", "putback", "guard",
                                        "guard-putback", "voice", "gate", "brain"])
    ap.add_argument("work")
    ap.add_argument("--roles", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--zip", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--sha", default="")
    ap.add_argument("--expect-sha", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--delta", default="")
    ap.add_argument("--expect", default="")
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.command in CHANGING and not a.check_only:
            with MachineLock(a):
                return dispatch(a)
        return dispatch(a)
    except Failed as e:
        say(f"!! {e}")
        result(command=a.command, role=a.role, failed=str(e))
        return 1
    except Exception as e:  # noqa: BLE001 -- said with where it came from, never a value from the frames
        say(f"!! {e.__class__.__name__}: {e}")
        say(f"   where: {where(e)}")
        result(command=a.command, role=a.role, failed=f"{e.__class__.__name__}: {e}", where=where(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
