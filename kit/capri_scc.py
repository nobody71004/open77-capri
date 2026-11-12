"""The game's own Redscript compiler on a Capri package, the way a player's game will run it -- before any player
gets the package (Windows; run by capri_kit.py in a process of its own).

    python capri_scc.py --zip PACKAGE.zip --label NAME --out FOLDER [--game "C:\\...\\Cyberpunk 2077"]

It builds a sandbox in FOLDER\\NAME-<time>: r6\\cache holds the game's pristine script bundle (r6\\cache\\
final.redscripts -- REDscript 1.0 keeps the game's own one there and writes its output to .modded); r6\\scripts
holds this PC's scripts (every mod the server's launcher layer and the player have) with the package's own in
place of whatever Capri this PC has; extra\\ holds a copy of the scripts the game's RED4ext plugins add (ArchiveXL,
TweakXL, Mod Settings... -- read from the game's own last compile log, so the list is the game's).  Then it calls
the game's engine\\tools\\scc_lib.dll -- the compiler the game runs at every start -- on that sandbox.  Nothing in
the game folder is read for writing: the compiler sees copies only.

The compiler opens windows of its own: "REDscript error" (switched off here) and "REDscript migration" (when
scripts need rewriting for this REDscript; it cannot be switched off).  A watch on this process closes any such
window within half a second with Cancel -- the check then fails and says so -- so no window waits on the desktop.

Prints "SCC ..." lines and one "SCC-RESULT {json}" line: ok, the number of files, the errors (first 20 lines of
each), warnings, whether the compiler asked for a migration.  Exit 0 compiled, 1 refused by the compiler (or it
asked for a migration), 2 could not check (no game, no compiler, a dependency missing on this PC).
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import zipfile

CAPRI_DIR = "r6/scripts/CapriPersonalityConstruct/"
DEPS = ("RedHttpClient", "RedFileSystem", "RedData")
TIMEOUT = 240


def say(text):
    for line in str(text).splitlines() or [""]:
        print("SCC " + line, flush=True)


def done(code, **kw):
    print("SCC-RESULT " + json.dumps(kw, sort_keys=True), flush=True)
    return code


def default_games():
    out = []
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files")):
        out.append(os.path.join(base, "Steam", "steamapps", "common", "Cyberpunk 2077"))
        out.append(os.path.join(base, "GOG Galaxy", "Games", "Cyberpunk 2077"))
    vdf = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam", "steamapps",
                       "libraryfolders.vdf")
    try:
        for m in re.finditer(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="replace").read()):
            out.append(os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps", "common", "Cyberpunk 2077"))
    except OSError:
        pass
    return out


def find_game(given):
    for g in ([given] if given else []) + default_games():
        if g and os.path.isfile(os.path.join(g, "bin", "x64", "Cyberpunk2077.exe")):
            return os.path.abspath(g)
    return None


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def package_scripts(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        out = {}
        for n in z.namelist():
            p = n.replace("\\", "/")
            if p.startswith("r6/scripts/") and p.endswith(".reds") and ".." not in p.split("/"):
                out[p] = z.read(n)
        return out


def game_extra_scripts(game):
    """The scripts the game compiles from outside r6\\scripts (what its RED4ext plugins add), as the game's own last
    compile log lists them; without a log, every .reds under red4ext\\plugins\\*\\Scripts and red4ext\\plugins\\*\\."""
    log = os.path.join(game, "r6", "logs", "redscript_rCURRENT.log")
    found = []
    try:
        text = open(log, encoding="utf-8", errors="replace").read()
        blocks = re.split(r"^\[INFO[^\]]*\] Compiling \d+ files:\s*$", text, flags=re.M)
        if len(blocks) > 1:
            for line in blocks[-1].splitlines():
                if line.startswith("["):
                    break
                p = line.strip()
                if p and p.lower().endswith(".reds") and not p.lower().startswith("r6\\scripts\\"):
                    full = p if os.path.isabs(p) else os.path.join(game, p)
                    if os.path.isfile(full):
                        found.append(full)
    except OSError:
        pass
    if found:
        return found, "the game's own last compile log"
    plugins = os.path.join(game, "red4ext", "plugins")
    for d in sorted(os.listdir(plugins)) if os.path.isdir(plugins) else []:
        base = os.path.join(plugins, d)
        for f in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            if f.lower().endswith(".reds"):
                found.append(os.path.join(base, f))
        for dirpath, _, files in os.walk(os.path.join(base, "Scripts")):
            found += [os.path.join(dirpath, f) for f in sorted(files) if f.lower().endswith(".reds")]
    return found, "red4ext\\plugins (no compile log of the game's)"


def pristine_bundle(game):
    cache = os.path.join(game, "r6", "cache")
    for name in ("final.redscripts.bk", "final.redscripts"):
        p = os.path.join(cache, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"the game's script bundle is not in {cache}")


def build_sandbox(game, scripts, sandbox):
    """sandbox\\r6 (cache: the pristine bundle as final.redscripts, the 1.0 layout -- no .bk, which would make the
    compiler think of an older REDscript; scripts: this PC's without any Capri, then the package's; logs) and
    sandbox\\extra (copies of the plugins' scripts).  Returns a dict of what went in."""
    pristine = pristine_bundle(game)
    r6 = os.path.join(sandbox, "r6")
    for d in ("cache", "scripts", "logs"):
        os.makedirs(os.path.join(r6, d), exist_ok=True)
    shutil.copyfile(pristine, os.path.join(r6, "cache", "final.redscripts"))
    src = os.path.join(game, "r6", "scripts")
    theirs = {p.lower() for p in scripts}
    n_game = 0
    for dirpath, dirnames, filenames in os.walk(src):
        for f in filenames:
            if not f.lower().endswith(".reds"):
                continue
            full = os.path.join(dirpath, f)
            rel = "r6/scripts/" + os.path.relpath(full, src).replace("\\", "/")
            if rel.lower().startswith(CAPRI_DIR.lower()) or rel.lower() in theirs:
                continue            # Capri comes from the package alone
            dest = os.path.join(sandbox, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(full, dest)
            n_game += 1
    for rel, data in scripts.items():
        dest = os.path.join(sandbox, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    extra, where = game_extra_scripts(game)
    for i, full in enumerate(extra):
        rel = os.path.relpath(full, game)
        if rel.startswith("..") or os.path.isabs(rel):
            rel = os.path.join("outside", f"{i:03d}-{os.path.basename(full)}")      # (never outside the sandbox)
        dest = os.path.join(sandbox, "extra", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(full, dest)
    return {"game_files": n_game, "package_files": len(scripts), "extra": [os.path.relpath(p, game) for p in extra],
            "extra_from": where, "bundle": os.path.relpath(pristine, game), "bundle_size": os.path.getsize(pristine),
            "bundle_sha": sha16(pristine)}


class WindowWatch(threading.Thread):
    """Closes (Cancel) any window of this process whose title starts with REDscript, twice a second."""

    def __init__(self):
        super().__init__(daemon=True)
        self.closed = []
        self.stop = threading.Event()

    def run(self):
        if os.name != "nt":
            return
        user32 = ctypes.windll.user32
        pid = os.getpid()
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def each(hwnd, _):
            owner = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 256)
                if buf.value.startswith("REDscript"):
                    self.closed.append(buf.value)
                    user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0111, 2, 0)    # WM_COMMAND, IDCANCEL
            return True
        cb = proto(each)
        while not self.stop.is_set():
            try:
                user32.EnumWindows(cb, 0)
            except OSError:
                pass
            self.stop.wait(0.5)


def compile_sandbox(tools, r6, extra_dir):
    """scc_lib.dll, as scc.exe calls it, with the error window off.  (ok, the compiler's error text)."""
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(tools)
    lib = ctypes.CDLL(os.path.join(tools, "scc_lib.dll"))
    vp, cp = ctypes.c_void_p, ctypes.c_char_p
    lib.scc_settings_new.restype = vp
    lib.scc_settings_new.argtypes = [cp]
    lib.scc_settings_set_custom_cache_file.argtypes = [vp, cp]
    lib.scc_settings_set_custom_cache_file.restype = None
    lib.scc_settings_add_script_path.argtypes = [vp, cp]
    lib.scc_settings_add_script_path.restype = None
    lib.scc_settings_disable_error_popup.argtypes = [vp]
    lib.scc_settings_disable_error_popup.restype = None
    lib.scc_compile.restype = vp
    lib.scc_compile.argtypes = [vp]
    lib.scc_get_success.restype = vp
    lib.scc_get_success.argtypes = [vp]
    lib.scc_copy_error.restype = ctypes.c_size_t
    lib.scc_copy_error.argtypes = [vp, cp, ctypes.c_size_t]
    lib.scc_free_result.argtypes = [vp]
    lib.scc_free_result.restype = None
    settings = lib.scc_settings_new(r6.encode("utf-8"))      # the r6 folder: the compiler takes its parent as root
    lib.scc_settings_set_custom_cache_file(settings, os.path.join(r6, "cache", "final.redscripts").encode("utf-8"))
    if os.path.isdir(extra_dir):
        lib.scc_settings_add_script_path(settings, extra_dir.encode("utf-8"))
    lib.scc_settings_disable_error_popup(settings)
    res = lib.scc_compile(settings)
    ok = bool(lib.scc_get_success(res))
    err = ""
    if not ok:
        buf = ctypes.create_string_buffer(65536)
        n = lib.scc_copy_error(res, buf, len(buf))
        err = buf.raw[:min(n, len(buf))].decode("utf-8", errors="replace")
    lib.scc_free_result(res)
    return ok, err


def read_log(r6):
    logs = os.path.join(r6, "logs")
    paths = sorted((os.path.join(logs, f) for f in os.listdir(logs) if f.lower().startswith("redscript")),
                   key=os.path.getmtime) if os.path.isdir(logs) else []
    if not paths:
        return {"log": None}
    text = open(paths[-1], encoding="utf-8", errors="replace").read()
    blocks, cur = [], None
    for line in text.splitlines():
        if re.match(r"^\[(INFO|WARN|ERROR|DEBUG)\b", line):
            if cur and cur[0] == "ERROR":
                blocks.append("\n".join(cur[1][:20]))
            cur = (re.match(r"^\[(\w+)", line).group(1), [line])
        elif cur:
            cur[1].append(line)
    if cur and cur[0] == "ERROR":
        blocks.append("\n".join(cur[1][:20]))
    m = re.findall(r"Completed with (\d+) warnings? and (\d+) errors?", text)
    files = re.findall(r"Compiling (\d+) files", text)
    return {"log": paths[-1], "errors": blocks[:12], "error_count": int(m[-1][1]) if m else len(blocks),
            "warnings": int(m[-1][0]) if m else None, "files": int(files[-1]) if files else None,
            "migrated": re.findall(r"Applied \d+ migration changes to '[^']*'", text),
            "last": [l for l in text.splitlines() if l.startswith("[INFO")][-3:]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--game", default="")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    game = find_game(a.game)
    if not game:
        say("!! Cyberpunk 2077 is not on this PC where it was looked for (pass --game)")
        return done(2, ok=False, why="no game")
    tools = os.path.join(game, "engine", "tools")
    if not os.path.isfile(os.path.join(tools, "scc_lib.dll")):
        say(f"!! the game has no Redscript compiler ({tools}\\scc_lib.dll): is Redscript installed?")
        return done(2, ok=False, why="no compiler")
    scripts = package_scripts(a.zip)
    if not any(p.lower().startswith(CAPRI_DIR.lower()) for p in scripts):
        say("!! the package has no Capri scripts")
        return done(2, ok=False, why="no Capri scripts in the package")
    sandbox = os.path.join(a.out, f"{a.label}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(sandbox, exist_ok=True)
    try:
        info = build_sandbox(game, scripts, sandbox)
    except OSError as e:
        say(f"!! the sandbox could not be made: {e}")
        return done(2, ok=False, why=f"sandbox: {e}")
    r6 = os.path.join(sandbox, "r6")
    have = {d.lower() for d in os.listdir(os.path.join(r6, "scripts"))}
    missing = [d for d in DEPS if d.lower() not in have]
    say(f"{a.label}: {info['package_files']} script(s) from the package, {info['game_files']} from this PC's game "
        f"({game}), {len(info['extra'])} its plugins add ({info['extra_from']}: "
        f"{', '.join(os.path.basename(p) for p in info['extra']) or 'none'}); the game's bundle {info['bundle']}, "
        f"{info['bundle_size']} B, sha256 {info['bundle_sha']}...")
    if missing:
        say(f"!! this PC's game has no {', '.join(missing)} scripts: they come with XyberRP's launcher layer -- join "
            f"XyberRP or Staging once with the Open77 launcher, quit, and run this again")
        return done(2, ok=False, why="missing " + ", ".join(missing), sandbox=sandbox)
    watch = WindowWatch()
    watch.start()
    box = {}

    def work():
        try:
            box["ok"], box["err"] = compile_sandbox(tools, r6, os.path.join(sandbox, "extra"))
        except (OSError, AttributeError) as e:
            box["fail"] = f"{e.__class__.__name__}: {e}"
    t0 = time.time()
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(TIMEOUT)
    watch.stop.set()
    took = round(time.time() - t0, 1)
    if worker.is_alive():
        say(f"!! the compiler did not finish in {TIMEOUT} s (windows closed: {watch.closed or 'none'}): not checked")
        print("SCC-RESULT " + json.dumps({"ok": False, "why": "timeout", "label": a.label, "sandbox": sandbox}), flush=True)
        os._exit(2)
    if "fail" in box:
        say(f"!! the compiler could not be called: {box['fail']}")
        return done(2, ok=False, why=f"compiler: {box['fail']}", sandbox=sandbox)
    ok, err = box["ok"], box["err"]
    log = read_log(r6)
    asked = [w for w in watch.closed if "migration" in w.lower()]
    # this check's own copy of the game's bundle (~20 MB) and the compiler's output: not kept; the log and the
    # scripts stay in the sandbox for a look
    for f in ("final.redscripts", "final.redscripts.bk", "final.redscripts.modded"):
        try:
            os.remove(os.path.join(r6, "cache", f))
        except OSError:
            pass
    if asked or log.get("migrated"):
        say(f"{a.label}: !! the compiler wanted to MIGRATE scripts (rewrite them for this REDscript) -- its window was "
            f"closed with Cancel: these scripts are not what this REDscript compiles as they are")
        ok = False
    if ok:
        say(f"{a.label}: COMPILES with the game's own Redscript, nothing to migrate ({log.get('files')} files, "
            f"{log.get('warnings')} warning(s), 0 errors, {took} s)")
    else:
        say(f"{a.label}: !! the game's Redscript REFUSES it ({log.get('error_count')} error(s), {took} s):")
        for b in log.get("errors") or ([err[:2000]] if err else []):
            say("  " + b.replace("\n", "\n  "))
    for l in log.get("last") or []:
        say("  " + l)
    return done(0 if ok else 1, ok=ok, label=a.label, files=log.get("files"), warnings=log.get("warnings"),
                errors=log.get("errors") or ([err[:2000]] if err else []), migration_asked=bool(asked),
                windows=watch.closed, sandbox=sandbox, log=log.get("log"), seconds=took, extra=info["extra"])


if __name__ == "__main__":
    sys.exit(main())
