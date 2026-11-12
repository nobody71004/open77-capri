"""XyberRP's Capri thinking with the brain on the game servers' machine, for every player: a kit the owner runs
on the PC that has the fivem2open77 Studio (its SSH code, keys and Python) and the game.

    python capri_kit.py check   [--roles staging,production] --host USER@HOST --key-from STUDIO_ID
        READ ONLY.  On the machine (remote/capri_server.py look): both servers' Capri package -- is the brain wired
        in --, players on, the manifest players get; the brain: where nginx serves it (its secret path never shown),
        its per-address limits, the unit behind it, its health, its last requests, Ollama and its models, the web
        server's log of requests to it.  From this PC, the way a player's game reaches it: its models, and one short
        question with the time it took.  This PC's own Capri: its files, what its settings think with (no key), what
        the wiring decided at its last start (server_brain.json), its last requests to the brain.
    python capri_kit.py publish --role staging|production [--force] [--hook auto|wrap|patch] [--game DIR] --host ...
        The package ROLE hands out now (copied from the machine, its hash checked) with Capri.ServerBrain.reds added
        (the brain's address as nginx serves it, checked from this PC first), compiled with the game's own Redscript
        on this PC -- the live package first (it must compile here, or nothing can be judged), then the new one
        (the patch way: one call where Capri.Storage.reds's LoadSettings returns; the wrap way, which REDscript
        1.0 refuses for Capri's own methods, only as the fallback) -- and only then sent, put in
        ROLE's hosted store and named in its server.jsonc (refused with players on, unless --force; refused when the
        live build changed meanwhile).  ROLE is restarted afterwards by the bat (av_kit.py restart).
    python capri_kit.py verify  --role ROLE --host ...        READ ONLY, after the restart: what players get now
    python capri_kit.py putback --role ROLE [--force] --host ...  ROLE's Capri entry back to the build before
    python capri_kit.py guard   --host ...                    per-address limits on the brain's nginx location
    python capri_kit.py guard-putback --host ...              the brain's nginx site as it was before them
    python capri_kit.py player  [--game DIR]                  READ ONLY, no server: this PC's Capri (as in check)
    python capri_kit.py voice   [--role ROLE] --host ...      her own voice for every player, on the machine
        (remote/capri_voice_server.py: Pocket TTS 4.0.1 with her voice states from ROLE's package, its own unit and
        an nginx location with a private path and per-address limits; nothing when it is there and answering);
        then asked from this PC the way a player's Capri Voz asks it: one line in English, one in Spanish.
    python capri_kit.py gate    --role ROLE --host ...        ROLE's Mass Override gate updated (remote/gate/): every
        game polls it from its start and runs everyone's casts; asked from this PC afterwards.
    publish (1.16.17) also puts into the package: Mass Override's two scripts with ROLE's gate in them (every player
        runs every cast, template/mass-override/), and Capri Voz speaking with her voice from the machine
        (capri_voz.py: servidor.json added, CapriVoz.ps1 and its Linux twin edited, the edits checked by PowerShell's
        own parser here) -- refused while her voice is not on the machine.

Exit 0 done; 3 nothing changed (players on, or the live build changed: run it again); 5 the brain is already wired
in with this address (nothing to do); 1 something failed; 2 this PC cannot check the package (no game/compiler).
Everything goes to capri-<command>-<time>.log next to this file.  The brain's address is a capability: no line
of any log holds its path, nor any server address, nor any key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capri_wire as W  # noqa: E402
import capri_mo as MO  # noqa: E402
import capri_voz as Z  # noqa: E402

REMOTE = os.path.join(HERE, "remote", "capri_server.py")
EXTRAS = {"voice": [os.path.join(HERE, "remote", "capri_voice_server.py")],
          "gate": [os.path.join(HERE, "remote", "gate", "gate.js"), os.path.join(HERE, "remote", "gate", "dev-server.js")]}
SCC = os.path.join(HERE, "capri_scc.py")
SECRET_RX = re.compile(r"capri-brain-[0-9A-Za-z]{6,}")
VOICE_SECRET_RX = re.compile(r"capri-voice-[0-9A-Za-z]{6,}")
IPV4_RX = re.compile(r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
ALREADY = 5
ROLE_NAMES = {"staging": "open77-xbuniverse-staging", "production": "open77-xbuniverse"}


def clean(text) -> str:
    text = VOICE_SECRET_RX.sub("capri-voice-<secret>", SECRET_RX.sub("capri-brain-<secret>", str(text)))
    return IPV4_RX.sub("<addr>", text)


class Log:
    def __init__(self, path):
        self.path = path
        open(path, "w", encoding="utf-8").close()

    def __call__(self, text, quiet=False):
        line = f"[{time.strftime('%H:%M:%S')}] {clean(text)}"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if not quiet:
            print(line, flush=True)


class Failed(Exception):
    pass


def _av_kit_dir():
    for d in (os.environ.get("O77_AV_KIT", ""), os.path.join(HERE, "..", "open77-av-kit"),
              os.path.join(HERE, "..", "..", "open77-av-kit"),
              os.path.join(os.path.expanduser("~"), "Downloads", "open77-av-kit")):
        if d and os.path.isfile(os.path.join(d, "av_kit.py")):
            return os.path.abspath(d)
    return None


def av():
    d = _av_kit_dir()
    if d is None:
        raise Failed("the AV kit (av_kit.py, with the Studio's SSH code) was not found: not in O77_AV_KIT, next to "
                     "this kit or in Downloads\\open77-av-kit")
    if d not in sys.path:
        sys.path.insert(1, d)
    import av_kit  # noqa: E402
    return av_kit


# ------------------------------------------------------------------------------------------------ the machine
class Machine:
    """One SSH session to the game servers' machine, the way av_kit.py (the Studio's SSH code) signs in."""

    def __init__(self, a, log, extra=()):
        self.av = av()
        self.log = log
        self.extra = [p for k in extra for p in EXTRAS[k]]
        hosts, secrets = self.av.load_hosts(a, lambda t, quiet=False: log(t, quiet=True))
        (_, group), = list(hosts.items())[:1]
        self.h = self.av.Host(group[0], secrets, lambda t, quiet=False: log(t, quiet=quiet))
        self.work = None

    def __enter__(self):
        self.work = self.h.workdir()
        self.h.put(REMOTE, posixpath.join(self.work, "capri_server.py"), 0o644)
        for p in self.extra:
            self.h.put(p, posixpath.join(self.work, os.path.basename(p)), 0o644)
        return self

    def __exit__(self, *exc):
        try:
            if self.work:
                self.h.run(f"rm -rf {self.av.q(self.work)}", tries=2)
        finally:
            self.h.drop()

    def call(self, *args, timeout=600):
        """remote/capri_server.py ARGS in the work folder: its CAPRI lines into the log, (exit, its result)."""
        res = {}

        def shown(s):
            for line in s.splitlines():
                line = line.rstrip()
                if line.startswith("CAPRI-RESULT "):
                    try:
                        res.update(json.loads(line[len("CAPRI-RESULT "):]))
                    except ValueError:
                        self.log("  (a result line that is not JSON)")
                elif line.startswith("CAPRI "):
                    self.log("  " + line[len("CAPRI "):][:700])
                elif line.strip():
                    self.log("  " + line[:700])
        cmd = (f"python3 {self.av.q(posixpath.join(self.work, 'capri_server.py'))} {args[0]} {self.av.q(self.work)} "
               + " ".join(self.av.q(str(x)) for x in args[1:]))
        code, _ = self.h.run(cmd, timeout=timeout, tries=1, on_line=shown)
        return code, res


# ------------------------------------------------------------------------------------------------ the brain, from here
def ask_brain(url, log, chat=True):
    """The brain the way a player's game asks it (HTTPS, the certificate checked): its models, then (chat) one short
    question.  True when both answered."""
    host = url.split("/")[2]
    ctx = ssl.create_default_context()
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "/models", headers={"Accept": "application/json"}),
                                    timeout=30, context=ctx) as r:
            body = json.loads(r.read().decode("utf-8", errors="replace"))
        ids = [m.get("id") for m in body.get("data") or [] if isinstance(m, dict)]
        log(f"  from this PC, as a player's game asks it: https://{host}/capri-brain-<secret>/v1/models -> 200 in "
            f"{time.time() - t0:.2f} s: {', '.join(ids)}")
        if "capri-brain" not in ids:
            log("  !! it does not offer the capri-brain model")
            return False
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f"  !! from this PC the brain does not answer: {clean(e)}")
        return False
    if not chat:
        return True
    body = json.dumps({"model": "capri-brain", "max_tokens": 24, "messages": [
        {"role": "system", "content": "You are Capri, V's personality construct. Answer in one short sentence."},
        {"role": "user", "content": "V says: Capri, can you hear me?"}]}).encode("utf-8")
    t0 = time.time()
    try:
        req = urllib.request.Request(url + "/chat/completions", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
            reply = json.loads(r.read().decode("utf-8", errors="replace"))
        text = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        log(f"  one short question from this PC: answered in {time.time() - t0:.1f} s by {reply.get('model')}: "
            f"{text.strip()[:160]!r}")
        return bool(text.strip())
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f"  !! the question from this PC got no answer after {time.time() - t0:.1f} s: {clean(e)}")
        return False


# ------------------------------------------------------------------------------------------------ her voice, from here
def wav_seconds(data: bytes) -> float:
    import io  # noqa: PLC0415
    import wave  # noqa: PLC0415
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / float(w.getframerate())


def ask_voice(url, log):
    """Her voice the way a player's Capri Voz asks it (HTTPS, the certificate checked): one line in English and one
    in Spanish, timed. True when both came back as audio in her own voice."""
    host = url.split("/")[2]
    ctx = ssl.create_default_context()
    ok = True
    for lang, text in (("en", "V, it's Capri. You hear me with my own voice now, from the server."),
                       ("es", "V, soy Capri. Ahora me oyes con mi propia voz, desde el servidor.")):
        body = json.dumps({"model": "capri-voice", "input": text, "voice": "capri", "language": lang,
                           "response_format": "wav"}).encode("utf-8")
        t0 = time.time()
        try:
            req = urllib.request.Request(url + "/audio/speech", data=body, method="POST",
                                         headers={"Content-Type": "application/json", "Accept": "audio/wav"})
            with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
                data = r.read()
                voice = r.headers.get("X-Capri-Voice")
                gen = r.headers.get("X-Capri-Generated-Ms")
            secs = wav_seconds(data)
            good = data[:4] == b"RIFF" and secs >= 1.0 and voice == "capri"
            log(f"  from this PC, as a player's Capri Voz asks it: https://{host}/capri-voice-<secret>/v1/audio/speech "
                f"({lang}) -> {len(data)} B, {secs:.1f} s of audio in {time.time() - t0:.1f} s (made in {gen} ms on "
                f"the server), voice {voice}" + ("" if good else "  !! not her own voice, or not audio"))
            ok = ok and good
        except (urllib.error.URLError, OSError, ValueError, EOFError) as e:
            log(f"  !! her voice did not answer from this PC ({lang}) after {time.time() - t0:.1f} s: {clean(e)}")
            ok = False
    return ok


def check_capri_voz(entries, log):
    """The edited Capri Voz checked here before anything is sent: CapriVoz.ps1 with PowerShell's own parser (no
    error), its Linux twin compiled by Python."""
    ok = True
    ps1 = entries.get(Z.PS1)
    if ps1 is not None and sys.platform == "win32":
        path = os.path.join(HERE, "_scc", "CapriVoz.check.ps1")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(ps1)
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
               "$e = $null; $t = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{path}', [ref]$t, [ref]$e); \"ERRORS $($e.Count)\"; $e | ForEach-Object {{ $_.Message }}"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            out = (p.stdout or "").strip()
            n = re.search(r"ERRORS (\d+)", out)
            if n and n.group(1) == "0":
                log(f"  CapriVoz.ps1 as edited: PowerShell's own parser finds no error ({len(ps1)} B)")
            else:
                ok = False
                log("  !! CapriVoz.ps1 as edited does not parse: " + " | ".join(out.splitlines()[:6]))
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"  (PowerShell's parser could not be asked: {e}; the build's own checks stand)")
    lin = entries.get(Z.LINUX)
    if lin is not None:
        try:
            compile(lin.decode("utf-8"), "capri_voz_linux.py", "exec")
            log("  capri_voz_linux.py as edited: Python compiles it")
        except (SyntaxError, UnicodeDecodeError) as e:
            ok = False
            log(f"  !! capri_voz_linux.py as edited does not compile: {e}")
    return ok


# ------------------------------------------------------------------------------------------------ this PC's Capri
def find_game(given=""):
    sys.path.insert(0, HERE)
    import capri_scc  # noqa: E402
    return capri_scc.find_game(given)


def game_capri_files(game):
    """This PC's Capri scripts by package path (the launcher's files as the game's REDscript left them: migrated)."""
    out = {}
    base = os.path.join(game or "", "r6", "scripts", "CapriPersonalityConstruct")
    for dirpath, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(".reds"):
                full = os.path.join(dirpath, f)
                out["r6/scripts/" + os.path.relpath(full, os.path.join(game, "r6", "scripts")).replace("\\", "/")] = \
                    open(full, "rb").read()
    return out


def player(game, log, brain_host=None):
    """This PC's Capri: the files the launcher put in, what the settings think with (no key), the wiring's last
    decision, and the newest RedHttpClient log's requests to the brain."""
    if not game:
        log("this PC: Cyberpunk 2077 not found (pass --game)")
        return
    capri = os.path.join(game, "r6", "scripts", "CapriPersonalityConstruct")
    have = os.path.isdir(capri)
    wired = os.path.join(capri, "Capri.ServerBrain.reds")
    log(f"this PC ({game}): Capri's scripts {'there' if have else 'NOT there (joined no world that requires Capri?)'}"
        + (f"; Capri.ServerBrain.reds {'there' if os.path.isfile(wired) else 'not there'}" if have else ""))
    if os.path.isfile(wired):
        v = W.wired_values(open(wired, "rb").read())
        log(f"  the wiring here: {v.get('Package')}, {v.get('World')}, host {v.get('Host')}, {v.get('hook')}")
    store = os.path.join(game, "r6", "storages", "CapriConstruct")
    try:
        s = json.load(open(os.path.join(store, "settings.json"), encoding="utf-8-sig"))
        url = s.get("localUrl") or ""
        host = url.split("/")[2] if "://" in url else url
        log(f"  settings.json: provider {s.get('provider')}, local AI at {host or '-'}"
            f"{' (the capri-brain path)' if 'capri-brain' in url else ''}, model {s.get('localModel') or '-'}; "
            f"Player2 key {'saved' if s.get('player2Key') else 'none'}")
    except (OSError, ValueError) as e:
        log(f"  settings.json: not read ({e.__class__.__name__}) -- Capri never started here, or a fresh install")
    try:
        d = json.load(open(os.path.join(store, "server_brain.json"), encoding="utf-8-sig"))
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(store, "server_brain.json"))))
        log(f"  the wiring's decision at the last start ({t}): thinks with {d.get('thinksWith')} -- {d.get('why')} "
            f"(the settings had {d.get('settingsHad')}; package {d.get('package')}, {d.get('world')})")
    except (OSError, ValueError):
        log("  server_brain.json: none yet (the wiring has not run on this PC)")
    logs = os.path.join(game, "red4ext", "logs")
    try:
        files = sorted((os.path.join(logs, f) for f in os.listdir(logs) if f.startswith("redhttpclient")),
                       key=os.path.getmtime)
    except OSError:
        files = []
    if files:
        text = open(files[-1], encoding="utf-8", errors="replace").read().splitlines()
        posts = [l for l in text if "capri-brain-" in l and ("POST" in l or "GET" in l)]
        codes = [l for l in text if re.search(r"(?i)status|response|HTTP/\d", l) and "RedHttpClient" in l][-4:]
        log(f"  RedHttpClient's newest log ({os.path.basename(files[-1])}): {len(posts)} request(s) to the brain"
            + (f"; the last: {clean(posts[-1].split('] ')[-1])[:160]}" if posts else ""))
        for l in codes:
            log("    " + clean(l)[:200])


# ------------------------------------------------------------------------------------------------ commands
def cmd_check(a, log):
    rc = 0
    with Machine(a, log) as m:
        log("===== the machine (read only)")
        code, res = m.call("look", "--roles", a.roles or "staging,production")
        if code != 0:
            rc = 1
        log("===== the brain from this PC (read only)")
        code, fres = m.call("fetch", "--role", "staging")
        url = None
        if code == 0:
            local = os.path.join(HERE, "work", f"brain-{time.strftime('%Y%m%d-%H%M%S')}.url")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            m.h.get(posixpath.join(m.work, "brain.url"), local)
            url = open(local, encoding="utf-8").read().strip()
            os.remove(local)
        if url:
            if not ask_brain(url, log):
                rc = 1
        else:
            log("  !! the brain's address could not be read from the machine")
            rc = 1
        if code == 0 and (fres.get("voice") or {}).get("languages"):
            log("===== her voice from this PC (read only)")
            local = os.path.join(HERE, "work", f"voice-{time.strftime('%Y%m%d-%H%M%S')}.url")
            m.h.get(posixpath.join(m.work, "voice.url"), local)
            voice_url = open(local, encoding="utf-8").read().strip()
            os.remove(local)
            if not ask_voice(voice_url, log):
                rc = 1
        else:
            log("  (her voice is not on the machine yet: " + str((fres.get("voice") or {}).get("why")) + ")")
    log("===== this PC's Capri (read only)")
    player(find_game(a.game), log)
    return rc


def compile_check(zip_path, label, a, log):
    """capri_scc.py in a process of its own (the compiler is native code): (exit, result)."""
    out = os.path.join(HERE, "_scc")
    os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, "-X", "utf8", SCC, "--zip", zip_path, "--label", label, "--out", out]
    if a.game:
        cmd += ["--game", a.game]
    res = {}
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"  !! the compile check could not run: {e}")
        return 2, {}
    quiet = 0
    for line in (p.stdout + p.stderr).splitlines():
        if line.startswith("SCC-RESULT "):
            try:
                res = json.loads(line[len("SCC-RESULT "):])
            except ValueError:
                pass
        elif line.startswith("SCC "):
            log("  " + line[4:][:700])
        elif line.strip():
            # the compiler's own console lines (its 600 warnings among them): in the sandbox's log, counted here
            quiet += 1
    if quiet:
        log(f"  (the compiler's own {quiet} console line(s) are in {res.get('log') or 'the sandbox'})", quiet=True)
    return p.returncode, res


def cmd_publish(a, log):
    role = a.role
    world_name = {"staging": "XyberRP Staging", "production": "XyberRP"}[role]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = os.path.join(HERE, "work", f"{role}-{stamp}")
    os.makedirs(work, exist_ok=True)
    with Machine(a, log) as m:
        log(f"===== 1. {world_name}'s Capri as it is now, and the brain (read only)")
        code, res = m.call("fetch", "--role", role)
        if code != 0 or not res.get("entry"):
            raise Failed(f"the machine could not hand over {world_name}'s package: {res.get('failed', code)}")
        entry = res["entry"]
        world = res.get("world") or world_name
        if res.get("online") and not a.force:
            log(f"  {res['online']} connection(s) on {world} now: NOTHING done (the new Capri reaches players at a "
                f"restart) -- leave {world} (quit to the menu) and run the bat again")
            return 3
        # only the live package's scripts and every file's hash come here (a few hundred KB): this PC's uplink is
        # slow (26 MB went at 13 KB/s, 2026-11-12), so the package itself is made on the machine (assemble)
        old_zip = os.path.join(work, f"capri-{role}-{entry['version']}-live-scripts.zip")
        m.h.get(posixpath.join(m.work, "scripts.zip"), old_zip)
        man_path = os.path.join(work, f"capri-{role}-{entry['version']}-live-manifest.json")
        m.h.get(posixpath.join(m.work, "manifest.json"), man_path)
        local_url = os.path.join(work, "brain.url")
        m.h.get(posixpath.join(m.work, "brain.url"), local_url)
        url = open(local_url, encoding="utf-8").read().strip()
        os.remove(local_url)
        voice_url = None
        if (res.get("voice") or {}).get("languages"):
            local_voice = os.path.join(work, "voice.url")
            m.h.get(posixpath.join(m.work, "voice.url"), local_voice)
            voice_url = open(local_voice, encoding="utf-8").read().strip()
            os.remove(local_voice)
        if not voice_url:
            raise Failed("her voice is not on the machine yet (" + str((res.get("voice") or {}).get("why")) + "): the "
                         "package would have no voice to name -- the bat installs it first (capri_kit.py voice)")
        old = open(old_zip, "rb").read()
        manifest = json.load(open(man_path, encoding="utf-8"))
        if manifest.get("sha256") != entry["sha256"]:
            raise Failed("the machine's list of the package's files is not of the build server.jsonc names")
        scripts = W.read_zip(old)
        bad = [n for n, b in scripts.items() if manifest["entries"].get(n) != W.sha256(b)]
        if bad or not scripts:
            raise Failed(f"the scripts copied here do not hash as the live package's: {bad[:3]}")
        log(f"  copied here: the live package's {len(scripts)} scripts ({len(old)} B) and the hashes of its "
            f"{len(manifest['entries'])} files (sha256 {entry['sha256'][:16]}... as named)")
        host = url.split("/")[2]
        log(f"===== 2. the brain from this PC, as a player's game will ask it ({host})")
        if not ask_brain(url, log):
            raise Failed("the brain does not answer from this PC: a player's Capri could not think with it either")
        log(f"===== 2b. her voice from this PC, as a player's Capri Voz will ask it")
        if not ask_voice(voice_url, log):
            raise Failed("her voice does not answer from this PC: a player's Capri Voz could not use it either")
        langs = Z.languages(manifest["entries"])

        def extras_for(v):
            return {"files": MO.render(role, v), "voice": {"url": voice_url, "langs": langs}}
        if res.get("wired_same") and not a.rebuild:
            # the same build again (the live version): nothing would change -> nothing to do
            game_now = find_game(a.game)
            try:
                _, same = W.build(old, url, host, world, entry["version"], "patch",
                                  game=game_capri_files(game_now) if game_now else {}, extras=extras_for(entry["version"]))
                if not same["changed"]:
                    log(f"  {world}'s package already has the brain, her voice and Mass Override for everyone, as this "
                        f"kit builds them: nothing to do")
                    return ALREADY
                log(f"  {world}'s package has the brain wired in, but not (all of) this build: "
                    + ", ".join(posixpath.basename(n) for n in same["changed"]))
            except W.BuildError as e:
                log(f"  (the live build could not be rebuilt as it is: {clean(e)})")
        version = W.bump(entry["version"])
        log(f"===== 3. Capri {version} for {world}: the live {entry['version']} + Capri.ServerBrain.reds, Mass Override "
            f"for every player (its gate: {MO.BASES[role][0].split('/', 3)[-1]}), Capri Voz speaking with her voice "
            f"from the server ({langs}), its scripts as REDscript migrates them, checked with the game's own Redscript "
            f"on this PC")
        game = find_game(a.game)
        here = game_capri_files(game) if game else {}
        base_zip = os.path.join(work, f"capri-{role}-{entry['version']}-live-migrated-scripts.zip")
        base_data, migrated, other = W.migrated_only(old, here)
        with open(base_zip, "wb") as f:
            f.write(base_data)
        if migrated:
            log(f"  REDscript migrates {len(migrated)} of the live package's Capri scripts at every start (and asks "
                f"each player first): this PC's game did, so the new package carries them migrated -- "
                + ", ".join(f"{posixpath.basename(n)} ({e} edit(s))" for n, e in migrated.items()))
        else:
            log("  none of the live package's Capri scripts differs from this PC's game by a migration"
                + (f" ({len(here)} of them here)" if here else " (no Capri scripts in this PC's game)"))
        if other:
            log(f"  !! this PC's game holds another version of {', '.join(posixpath.basename(n) for n in other)}: "
                f"the package's own are kept")
        code, base = compile_check(base_zip, f"{role}-{entry['version']}-live", a, log)
        if code != 0:
            hint = (" -- the compiler wanted to migrate Capri's scripts: start the game once with "
                    f"{world} joined (the launcher installs its Capri, the game migrates it), quit, and run this again"
                    if base.get("migration_asked") else "")
            raise Failed(f"the LIVE package does not compile with this PC's game (exit {code}): this PC cannot judge a "
                         f"new one -- nothing was sent (see the compiler's lines above){hint}")
        # patch first: REDscript 1.0 (preview.22) refuses @wrapMethod on Capri's own (scripted) LoadSettings --
        # "could not find a method with a matching signature" -- checked on the real compiler 2026-11-12
        hooks = ["patch", "wrap"] if a.hook == "auto" else [a.hook]
        chosen = None
        for hook in hooks:
            try:
                data, rep = W.build(old, url, host, world, version, hook, game=here, extras=extras_for(version))
            except W.BuildError as e:
                log(f"  {hook}: not built: {clean(e)}")
                continue
            new_zip = os.path.join(work, f"capri-{role}-{version}-{hook}-scripts.zip")
            with open(new_zip, "wb") as f:
                f.write(data)
            log(f"  {hook}: built the scripts ({rep['entries']}), {len(rep['changed'])} changed: "
                f"{', '.join(posixpath.basename(n) for n in rep['changed'])}")
            code, cres = compile_check(new_zip, f"{role}-{version}-{hook}", a, log)
            if code == 0 and cres.get("ok"):
                if not check_capri_voz(W.read_zip(data), log):
                    raise Failed("Capri Voz as edited does not pass its checks here: NOTHING was sent")
                chosen = (hook, new_zip, data, rep)
                break
            log(f"  {hook}: the compiler refuses it (exit {code})" + ("; the other way next" if hook != hooks[-1] else ""))
        if not chosen:
            raise Failed("no build compiles with the game's own Redscript: NOTHING was sent (the compiler's lines are "
                         "above, its log in the _scc folder here)")
        hook, new_zip, data, rep = chosen
        log(f"===== 4. Capri {version} ({hook}) to {world}: made on the machine, into its hosted store, named in "
            f"server.jsonc")
        # what goes up: only the scripts this build changed, and the hash every file of the package must have
        built = W.read_zip(data)
        delta = {n: built[n] for n in rep["changed"]}
        expect = dict(manifest["entries"])
        expect.update({n: W.sha256(b) for n, b in delta.items()})
        delta_zip = os.path.join(work, f"capri-{role}-{version}-{hook}-changes.zip")
        with open(delta_zip, "wb") as f:
            f.write(W.write_zip(delta))
        expect_json = os.path.join(work, f"capri-{role}-{version}-{hook}-expect.json")
        with open(expect_json, "w", encoding="utf-8") as f:
            json.dump(expect, f, indent=1, sort_keys=True)
        t0 = time.time()
        m.h.put(delta_zip, posixpath.join(m.work, "changes.zip"), 0o644)
        m.h.put(expect_json, posixpath.join(m.work, "expect.json"), 0o644)
        log(f"  sent: the {len(delta)} changed script(s) ({os.path.getsize(delta_zip)} B) and the hashes of all "
            f"{len(expect)} files, in {time.time() - t0:.1f} s")
        code, ares = m.call("assemble", "--role", role, "--delta", posixpath.join(m.work, "changes.zip"),
                            "--expect", posixpath.join(m.work, "expect.json"), "--expect-sha", entry["sha256"])
        if code != 0 or not ares.get("sha256"):
            raise Failed(f"the machine could not make the package as built here: {ares.get('failed') or code} -- "
                         f"NOTHING changed on {world}")
        args = ["import", "--role", role, "--zip", posixpath.join(m.work, "assembled.zip"),
                "--version", version, "--expect-sha", entry["sha256"]]
        if a.force:
            args.append("--force")
        code, ires = m.call(*args)
        if code == 3:
            return 3
        if code != 0 or not ires.get("changed"):
            raise Failed(f"{world} did not take the build: {ires.get('why') or ires.get('failed') or code}")
        record = {"role": role, "world": world, "version": version, "sha256": ares["sha256"],
                  "size": ares.get("sizeBytes"), "hook": hook, "from": entry, "at": stamp,
                  "changed": sorted(delta), "scripts_sha256": rep["scripts_sha256"], "host": host,
                  "migrated": rep.get("migrated"), "voice": rep.get("voice"), "mass_override": MO.BASES[role][1]}
        with open(os.path.join(HERE, f"last-{role}.json"), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        log(f"  {world} names Capri {version} now (sha256 {ares['sha256'][:16]}...); players get it from its next "
            f"start (the bat restarts it next)")
    return 0


def last_record(role):
    try:
        return json.load(open(os.path.join(HERE, f"last-{role}.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cmd_verify(a, log):
    rec = last_record(a.role)
    sha, version = a.sha or (rec or {}).get("sha256"), a.version or (rec or {}).get("version")
    if not sha or not version:
        log(f"  (no build of this kit is recorded here for {a.role}: the build the server names now is checked)")
        sha, version = "live", "live"
    voice_url = None
    with Machine(a, log) as m:
        code, res = m.call("verify", "--role", a.role, "--sha", sha, "--version", version)
        local = os.path.join(HERE, "work", f"voice-{time.strftime('%Y%m%d-%H%M%S')}.url")
        os.makedirs(os.path.dirname(local), exist_ok=True)
        try:
            m.h.get(posixpath.join(m.work, "voice.url"), local)
            voice_url = open(local, encoding="utf-8").read().strip()
        except Exception:  # noqa: BLE001 -- no voice there: verify said why
            voice_url = None
        finally:
            if os.path.exists(local):
                os.remove(local)
    voice_ok = True
    if voice_url:
        log("===== her voice from this PC, as a player's Capri Voz asks it")
        voice_ok = ask_voice(voice_url, log)
    if code == 0 and res.get("ok") and voice_ok:
        log(f"===== what players of {res.get('role')} get now: Capri {version}, the brain wired in, her voice from the "
            f"server, Mass Override for every player -- checked")
        return 0
    return 1


def cmd_voice(a, log):
    """Her voice for every player on the machine (remote/capri_server.py voice): once for the machine, then asked from
    this PC."""
    with Machine(a, log, extra=("voice",)) as m:
        log("===== her voice on the game servers' machine (Pocket TTS with her own voice states; once for the machine)")
        args = ["voice"] + (["--role", a.role] if a.role else [])
        code, res = m.call(*args, timeout=3600)
        url = None
        if code in (0, 3):
            local = os.path.join(HERE, "work", f"voice-{time.strftime('%Y%m%d-%H%M%S')}.url")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            m.h.get(posixpath.join(m.work, "voice.url"), local)
            url = open(local, encoding="utf-8").read().strip()
            os.remove(local)
    if code not in (0, 3) or not url:
        return 1
    log("===== her voice from this PC")
    return 0 if ask_voice(url, log) else 1


def cmd_gate(a, log):
    """ROLE's Mass Override gate updated (remote/capri_server.py gate), then asked from this PC."""
    with Machine(a, log, extra=("gate",)) as m:
        log(f"===== {a.role}'s Mass Override gate: every game gets every cast")
        code, res = m.call("gate", "--role", a.role)
    if code not in (0, 3):
        return 1
    return 0 if ask_gate(MO.BASES[a.role][0], log) else 1


def ask_gate(base, log):
    """The gate the way a game polls it (HTTPS, the certificate checked): GET /casts answers with its cursor."""
    t0 = time.time()
    try:
        with urllib.request.urlopen(base + "/casts?since=0&session=capri-kit-pc", timeout=30,
                                    context=ssl.create_default_context()) as r:
            text = r.read().decode("utf-8", errors="replace")
        first = text.splitlines()[0] if text else ""
        log(f"  from this PC, as a game polls it: {base.split('/', 3)[-1]}/casts -> 200 in {time.time() - t0:.2f} s "
            f"(cursor {first}, {max(0, len(text.splitlines()) - 1)} cast(s) on now)")
        return bool(re.match(r"^\d+$", first))
    except (urllib.error.URLError, OSError) as e:
        log(f"  !! the gate does not answer from this PC: {clean(e)}")
        return False


def cmd_guard(a, log):
    """Per-address limits on the brain's nginx location (remote/capri_server.py guard): machine-wide, once."""
    with Machine(a, log) as m:
        log("===== the brain's per-address limits (its private address now travels to every player)")
        code, res = m.call("guard-putback" if a.command == "guard-putback" else "guard")
    if code == 0:
        return 0
    if code == 3:
        log("  (nothing to do)")
        return 0
    return 1


def cmd_putback(a, log):
    with Machine(a, log) as m:
        args = ["putback", "--role", a.role] + (["--force"] if a.force else [])
        code, res = m.call(*args)
    if code == 0 and res.get("changed"):
        try:
            os.replace(os.path.join(HERE, f"last-{a.role}.json"),
                       os.path.join(HERE, f"last-{a.role}.json.put-back-{time.strftime('%Y%m%d-%H%M%S')}"))
        except OSError:
            pass
        return 0
    return code if code in (1, 3) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "publish", "verify", "putback", "player", "guard", "guard-putback",
                                        "voice", "gate"])
    ap.add_argument("--role", default="", choices=["", "staging", "production"])
    ap.add_argument("--roles", default="")
    ap.add_argument("--hook", default="auto", choices=["auto", "wrap", "patch"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rebuild", action="store_true", help="publish: even when the brain is wired in already")
    ap.add_argument("--sha", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--game", default="")
    ap.add_argument("--host", default="")
    ap.add_argument("--key-from", default="")
    ap.add_argument("--root", default="")
    ap.add_argument("--systemctl", default="")
    ap.add_argument("--sudo", action="store_true")
    ap.add_argument("--prefix", default="xyberrp")
    ap.add_argument("--workspace", default=os.environ.get("F2O77_WORKSPACE") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "fivem2open77", "studio"))
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    tag = a.command + (f"-{a.role}" if a.role else "")
    log = Log(os.path.join(HERE, f"capri-{tag}-{time.strftime('%Y%m%d-%H%M%S')}.log"))
    log(f"capri_kit {tag}: Python {sys.version.split()[0]} on {sys.platform}; log {log.path}")
    try:
        if a.command in ("publish", "verify", "putback", "gate") and not a.role:
            raise Failed("--role staging or production")
        if a.command != "player" and not (a.host and a.key_from):
            raise Failed("--host USER@HOST and --key-from STUDIO_ID (the bat gives them)")
        rc = {"check": cmd_check, "publish": cmd_publish, "verify": cmd_verify, "putback": cmd_putback,
              "guard": cmd_guard, "guard-putback": cmd_guard, "voice": cmd_voice, "gate": cmd_gate,
              "player": lambda a, log: (player(find_game(a.game), log) or 0)}[a.command](a, log)
    except (Failed, W.BuildError) as e:
        log(f"!! {e}")
        rc = 1
    except Exception as e:  # noqa: BLE001 -- the Studio's own errors and paramiko's
        log(f"!! {e.__class__.__name__}: {e}")
        rc = 1
    log(f"exit {rc}; the full log: {log.path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
