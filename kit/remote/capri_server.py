#!/usr/bin/env python3
"""XyberRP's Capri on the game servers' machine: what the kit on the owner's PC (capri_kit.py) asks of it.

    capri_server.py look    WORK [--roles staging,production]       READ ONLY: both servers' Capri package (is the
                            brain wired in?), the players on, the brain (nginx, its unit, Ollama, what it answers,
                            what it was asked lately)
    capri_server.py fetch   WORK --role ROLE                        READ ONLY: the package ROLE hands out now, into
                            WORK/capri-current.zip, and the brain's address as nginx serves it into WORK/brain.url
                            (0600; the kit reads it, nobody prints it)
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
import time
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
IPV4_RX = re.compile(r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
KEYISH_RX = re.compile(r"(?i)key|token|secret|pass|cred|auth")
NO = 3


class Failed(Exception):
    pass


def clean(text) -> str:
    text = SECRET_RX.sub("capri-brain-<secret>", str(text))
    return IPV4_RX.sub("<addr>", text)


def say(text=""):
    for line in str(text).splitlines() or [""]:
        print("CAPRI " + clean(line), flush=True)


def result(**kw):
    print("CAPRI-RESULT " + clean(json.dumps(kw, sort_keys=True)), flush=True)


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
    out["roles"] = []
    for role in [r.strip() for r in (a.roles or "staging,production").split(",") if r.strip()]:
        try:
            out["roles"].append(describe_role(role, cur))
        except (Failed, OSError, ValueError) as e:
            say(f"===== {role}: !! {e}")
            out["roles"].append({"role": role, "error": str(e)})
    result(command="look", **out)
    return 0


def cmd_fetch(a) -> int:
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
    fd = os.open(os.path.join(a.work, "brain.url"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(cur["url"] + "\n")
    look = zip_look(blob)
    who = online(root)
    say(f"{world}: Capri {entry.get('version')} ({look['files']} files, sha256 {sha[:16]}...) copied for the build; "
        f"the brain wired in already: {'yes, ' + ('the same address' if look.get('url') == cur['url'] else 'ANOTHER address') if look['wired'] else 'no'}"
        f"; players on: {len(who)}")
    say(f"the brain for players: {cur['host']}{clean(cur['base'])}v1 answers through nginx ({', '.join(cur['models'])})")
    result(command="fetch", role=a.role, world=world, root=root, unit=name + ".service",
           entry={k: entry.get(k) for k in ("version", "sha256", "sizeBytes", "displayName")},
           wired=look["wired"], wired_same=bool(look["wired"] and look.get("url") == cur["url"]),
           host=cur["host"], online=len(who), limit_req=cur["limit_req"])
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
    rx = re.compile(r"^([ \t]*)location[ \t]+(?:" + re.escape(cur["modifier"]) + r"[ \t]+)?" + re.escape(cur["path"])
                    + r"[ \t]*\{[ \t]*$", re.M)
    hits = list(rx.finditer(text))
    if len(hits) != 1:
        raise Failed(f"{real}: the brain's location line is there {len(hits)} times (one expected, on a line of its own)")
    code, all_conf = run(NGINX + ["-T"], timeout=30)
    zone_there = re.search(r"^\s*limit_req_zone\s.*zone=capri_brain:", all_conf, re.M) is not None
    conn_there = re.search(r"^\s*limit_conn_zone\s.*zone=capri_brain_conn:", all_conf, re.M) is not None
    if zone_there != conn_there:
        raise Failed("one of the two capri_brain zones is defined elsewhere, the other not: nothing changed")
    m = hits[0]
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["look", "fetch", "import", "verify", "putback", "guard", "guard-putback"])
    ap.add_argument("work")
    ap.add_argument("--roles", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--zip", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--sha", default="")
    ap.add_argument("--expect-sha", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.command == "look":
            return cmd_look(a)
        if a.command == "guard":
            return cmd_guard(a)
        if a.command == "guard-putback":
            return cmd_guard_putback(a)
        if not a.role:
            raise Failed("--role staging or production")
        return {"fetch": cmd_fetch, "import": cmd_import, "verify": cmd_verify, "putback": cmd_putback}[a.command](a)
    except Failed as e:
        say(f"!! {e}")
        result(command=a.command, role=a.role, failed=str(e))
        return 1
    except Exception as e:  # noqa: BLE001 -- said, never a traceback with paths of secrets
        say(f"!! {e.__class__.__name__}: {e}")
        result(command=a.command, role=a.role, failed=f"{e.__class__.__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
