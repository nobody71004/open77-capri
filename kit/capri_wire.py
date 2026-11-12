"""Capri's package with the server brain wired in: the build, and what must be true of it.

The XyberRP Capri package is an Open77 launcher package (requiredMods): a zip of game-root paths. This module
takes the package a server hands out now and adds r6/scripts/CapriPersonalityConstruct/Capri.ServerBrain.reds
(template/Capri.ServerBrain.reds with the brain's address, host, the world's name and the package's version
put in), so every player's Capri thinks with the brain on the game server's machine from the game's start.

Two ways of hooking it in, both checked by the game's own compiler before anything is published (capri_scc.py):
  patch  Capri.Storage.reds calls CapriServerBrain.Wire right where LoadSettings returns; its anchors must be
         exactly as expected or nothing is built.  The way that compiles: REDscript 1.0 (preview.22, the launcher's)
         compiles it with 0 errors (checked on the game's own compiler, 2026-11-12).
  wrap   the new file wraps CapriStorage.LoadSettings (@wrapMethod), Capri's files untouched -- REDscript 1.0
         refuses it for a method of a scripted class ("could not find a method with a matching signature"); kept
         for a REDscript that takes it.

Migrated scripts.  REDscript 1.0 (preview.22, what the launcher's layer installs) rewrites 12 of Capri 1.16's
files at every game start ("REDscript migration": `new Struct(` becomes `Struct(`, a few types become public) and
asks the player with a window first; the launcher puts the original files back at the next connect, so the window
comes back at every launch.  build() takes the migrated files the game itself wrote (this PC's game folder, after
one start with the layer) when they differ from the package's ONLY by those edits (is_migration_of), so the new
package needs no migration: no window, nothing rewritten, the compile check sees exactly what players compile.

Pure Python, no I/O but what it is given: the kit (capri_kit.py) and the tests drive it.  The brain's address is
a capability (its path is a secret): nothing here prints it; reports carry the host alone.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from pathlib import PurePosixPath

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(HERE, "template", "Capri.ServerBrain.reds")

CAPRI_DIR = "r6/scripts/CapriPersonalityConstruct"
TARGET = CAPRI_DIR + "/Capri.ServerBrain.reds"
STORAGE = CAPRI_DIR + "/Capri.Storage.reds"
MODEL = "capri-brain"
STRATEGIES = ("wrap", "patch")

# Same roots as the launcher (Open77.Launcher/ModStack/ModRootPolicy.Roots) and scripts/build_capri_launcher_mod.py.
MOD_ROOTS = (
    "bin/x64/plugins/cyber_engine_tweaks/mods", "red4ext/plugins", "bin/x64/plugins", "archive/pc/mod", "r6/scripts",
    "r6/tweaks", "r6/input", "r6/config", "engine/config", "engine/tools", "EasyAntiCheat", "mods", "bin/x64",
)
FIXED_TIME = (2026, 1, 1, 0, 0, 0)

URL_RX = re.compile(r"^https://([a-z0-9.-]{3,253})(/[A-Za-z0-9._~/-]{1,200})?/v1$")
HOST_RX = re.compile(r"^[a-z0-9.-]{3,253}$")
WORLD_RX = re.compile(r"^[A-Za-z0-9 ._-]{1,40}$")
VERSION_RX = re.compile(r"^\d{1,4}(\.\d{1,4}){1,4}$")
SECRET_RX = re.compile(r"capri-brain-[0-9A-Za-z]{6,}")

HOOK_WRAP = """
// Capri reads settings.json once, when the game starts (CapriStorage.OnInitialize): wired right after.
@wrapMethod(CapriStorage)
private func LoadSettings() -> ref<CapriSettingsDTO> {
    let s = wrappedMethod();
    if IsDefined(s) {
        CapriServerBrain.Wire(this, s);
    }
    return s;
}
"""
HOOK_PATCH = """
// Capri reads settings.json once, when the game starts (CapriStorage.OnInitialize): Capri.Storage.reds calls
// CapriServerBrain.Wire where LoadSettings returns (put in by the kit).
"""

# What the wiring leans on in Capri's own files: a package where any of this changed is not built.
REQUIRED_IN_STORAGE = (
    "module Capri",
    "public class CapriSettingsDTO",
    "public let provider: String;",
    "public let localUrl: String;",
    "public let localModel: String;",
    "public let openrouterKey: String;",
    "public let geminiKey: String;",
    "public let openaiKey: String;",
    "public let customUrl: String;",
    "public let customModel: String;",
    "public class CapriStorage extends ScriptableService",
    "private func LoadSettings() -> ref<CapriSettingsDTO> {",
    "this.settings = this.LoadSettings();",
    "public func WriteFile(fileName: String, text: String) -> Bool {",
)
# Patch: the end of LoadSettings, exactly (Capri 1.16).
PATCH_ANCHOR = "        return s;\n    }\n\n    public func SaveSettings() -> Void {"
PATCH_WITH = ("        // XyberRP: the server's brain (Capri.ServerBrain.reds, put in by the XyberRP Capri kit)\n"
              "        CapriServerBrain.Wire(this, s);\n" + PATCH_ANCHOR)
PATCH_MARK = "CapriServerBrain.Wire(this, s);"


class BuildError(Exception):
    pass


def mask(text: str) -> str:
    """Anything that looks like the brain's secret path, hidden."""
    return SECRET_RX.sub("capri-brain-<secret>", text)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(name: str) -> str:
    path = name.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.strip("/")


def refusal(path: str) -> str | None:
    if not path or path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return "an absolute path"
    if any(part in ("", ".", "..") for part in PurePosixPath(path).parts):
        return "a path that climbs out"
    if not any(path == r or path.startswith(r + "/") for r in MOD_ROOTS):
        return "outside every Open77 mod root"
    if path.lower().startswith("r6/storages/"):
        return "player storage"
    return None


def read_zip(data: bytes) -> dict[str, bytes]:
    """The package's files by game-root path (folders left out); a path the launcher would refuse, or twice, refused."""
    entries: dict[str, bytes] = {}
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise BuildError(f"the package is not a zip: {e}") from e
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalize(info.filename)
            why = refusal(name)
            if why:
                raise BuildError(f"the package has {name!r}: {why}")
            if name in entries:
                raise BuildError(f"the package has {name!r} twice")
            entries[name] = archive.read(info)
    return entries


def write_zip(entries: dict[str, bytes]) -> bytes:
    """Reproducible: the same files always make the same bytes (sorted, one fixed time), as the package builders do."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name])
    return out.getvalue()


def check_inputs(url: str, host: str, world: str, version: str) -> None:
    m = URL_RX.match(url or "")
    if not m:
        raise BuildError("the brain's address is not https://HOST/PATH/v1")
    if m.group(1) != host or not HOST_RX.match(host or ""):
        raise BuildError("the brain's host does not match its address")
    if not WORLD_RX.match(world or ""):
        raise BuildError(f"the world's name {world!r} is not plain")
    if not VERSION_RX.match(version or ""):
        raise BuildError(f"the version {version!r} is not N.N.N")


def render(url: str, host: str, world: str, version: str, strategy: str) -> bytes:
    """template/Capri.ServerBrain.reds with the values put in (UTF-8, LF)."""
    check_inputs(url, host, world, version)
    if strategy not in STRATEGIES:
        raise BuildError(f"no such way of hooking it in: {strategy}")
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    for key in ("@@PACKAGE@@", "@@WORLD@@", "@@URL@@", "@@HOST@@", "@@HOOK@@"):
        if key not in text:
            raise BuildError(f"the template has no {key}")
    text = (text.replace("@@PACKAGE@@", version).replace("@@WORLD@@", world).replace("@@URL@@", url)
            .replace("@@HOST@@", host).replace("@@HOOK@@", HOOK_WRAP if strategy == "wrap" else HOOK_PATCH))
    if "@@" in text:
        raise BuildError("the template has a placeholder left")
    if text.count(url) != 1:
        raise BuildError("the brain's address is not in the script exactly once")
    return text.encode("utf-8")


def wired_values(reds: bytes) -> dict[str, str]:
    """What a Capri.ServerBrain.reds says (Package, World, Url, Host, Model); {} when it is not one."""
    text = reds.decode("utf-8", errors="replace")
    out = {}
    for key in ("Package", "World", "Url", "Host", "Model"):
        m = re.search(r"public static func " + key + r"\(\) -> String \{ return \"([^\"]*)\"; \}", text)
        if m:
            out[key] = m.group(1)
    if "class CapriServerBrain" not in text:
        return {}
    out["hook"] = "wrap" if "@wrapMethod(CapriStorage)" in text else "patch"
    return out


def capri_problems(entries: dict[str, bytes]) -> list[str]:
    """What the wiring needs from Capri's own files that this package does not have."""
    storage = entries.get(STORAGE)
    if storage is None:
        return [f"{STORAGE} is not in the package"]
    text = storage.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return [f"{STORAGE} no longer has: {need}" for need in REQUIRED_IN_STORAGE if need not in text]


def bump(version: str) -> str:
    """1.16.15 -> 1.16.16 (the last number up)."""
    if not VERSION_RX.match(version or ""):
        raise BuildError(f"the live version {version!r} is not N.N.N")
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def build(old: bytes, url: str, host: str, world: str, version: str, strategy: str,
          game: dict[str, bytes] | None = None) -> tuple[bytes, dict]:
    """The new package from the live one: Capri.ServerBrain.reds added (an older one replaced), the scripts the game
    migrates put in migrated (game: this PC's game folder's Capri files, see migrate) and, for "patch", the one call
    in Capri.Storage.reds.  Returns (zip bytes, report).  Everything else stays byte for byte."""
    entries = read_zip(old)
    problems = capri_problems(entries)
    if problems:
        raise BuildError("; ".join(problems))
    before = dict(entries)
    migrated, other = migrate(entries, game)
    had = wired_values(entries[TARGET]) if TARGET in entries else {}
    try:
        storage = entries[STORAGE].decode("utf-8")
    except UnicodeDecodeError as e:
        raise BuildError(f"{STORAGE} is not UTF-8: {e}") from e
    if PATCH_MARK in storage or strategy == "patch":
        crlf = "\r\n" in storage
        plain = storage.replace("\r\n", "\n")
        if PATCH_MARK in plain:
            # an earlier patch build: back to Capri's own file first
            plain = plain.replace(PATCH_WITH, PATCH_ANCHOR)
            if PATCH_MARK in plain:
                raise BuildError(f"{STORAGE} calls CapriServerBrain.Wire in a way this kit did not write")
        if strategy == "patch":
            if plain.count(PATCH_ANCHOR) != 1:
                raise BuildError(f"{STORAGE}: the end of LoadSettings is not exactly as expected (patch refused)")
            plain = plain.replace(PATCH_ANCHOR, PATCH_WITH)
        entries[STORAGE] = (plain.replace("\n", "\r\n") if crlf else plain).encode("utf-8")
    entries[TARGET] = render(url, host, world, version, strategy)
    data = write_zip(entries)

    # what the zip holds now, read back
    after = read_zip(data)
    changed = sorted(n for n in after if after[n] != before.get(n))
    gone = sorted(n for n in before if n not in after)
    allowed = {TARGET, STORAGE} | set(migrated)
    if gone:
        raise BuildError(f"the build lost {gone}")
    if not set(changed) <= allowed:
        raise BuildError(f"the build changed more than it should: {sorted(set(changed) - allowed)}")
    values = wired_values(after[TARGET])
    if values.get("Url") != url or values.get("Host") != host or values.get("Package") != version \
            or values.get("World") != world or values.get("Model") != MODEL or values.get("hook") != strategy:
        raise BuildError("the script in the build does not say what was put in")
    if strategy == "patch" and after[STORAGE].decode("utf-8").count(PATCH_MARK) != 1:
        raise BuildError("the patched Capri.Storage.reds does not call the wiring exactly once")
    if strategy == "wrap" and PATCH_MARK in after[STORAGE].decode("utf-8"):
        raise BuildError("a wrap build still has the patch in Capri.Storage.reds")
    report = {
        "entries": len(after),
        "changed": changed,
        "sha256": sha256(data),
        "size": len(data),
        "version": version,
        "world": world,
        "host": host,
        "hook": strategy,
        "had": {k: (v if k != "Url" else ("the same address" if v == url else "another address")) for k, v in had.items()},
        "migrated": migrated,
        "other_version_here": other,
        "scripts_sha256": scripts_digest(after),
    }
    return data, report


def scripts_of(entries: dict[str, bytes]) -> dict[str, bytes]:
    return {n: b for n, b in entries.items() if n.startswith("r6/scripts/") and n.endswith(".reds")}


def scripts_digest(entries: dict[str, bytes]) -> str:
    """One digest over the package's Redscript files (paths and bytes): what the compile check saw is what ships."""
    h = hashlib.sha256()
    for name in sorted(scripts_of(entries)):
        h.update(name.encode("utf-8") + b"\0" + hashlib.sha256(entries[name]).digest())
    return h.hexdigest()


NEW_RX = re.compile(r"\bnew\s+")
VIS_RX = re.compile(r"\b(?:public|private|protected)\s+")


def is_migration_of(original: bytes, migrated: bytes) -> int:
    """How many edits REDscript's migration made to turn `original` into `migrated` (removed `new`s before a
    struct's name, a visibility made public); 0 when `migrated` is not that (the same file, or other changes)."""
    if original == migrated:
        return 0
    try:
        a, b = original.decode("utf-8"), migrated.decode("utf-8")
    except UnicodeDecodeError:
        return 0
    if a.count("\n") != b.count("\n"):
        return 0
    if NEW_RX.sub("", VIS_RX.sub("", a)) != NEW_RX.sub("", VIS_RX.sub("", b)):
        return 0
    removed = len(NEW_RX.findall(a)) - len(NEW_RX.findall(b))
    publics = len(re.findall(r"\bpublic\s+", b)) - len(re.findall(r"\bpublic\s+", a))
    if removed < 0 or publics < 0:
        return 0
    return removed + publics or 1


def migrate(entries: dict[str, bytes], game: dict[str, bytes] | None) -> tuple[dict[str, int], list[str]]:
    """In place: every Capri script the game migrated (game: this PC's game folder's files by package path) put in
    as the game wrote it.  Returns ({path: edits}, [paths the game folder holds in another version: kept])."""
    done, other = {}, []
    for name in sorted(n for n in entries if n.startswith(CAPRI_DIR + "/") and n.endswith(".reds")):
        if name == TARGET or not game or name not in game or game[name] == entries[name]:
            continue
        n = is_migration_of(entries[name], game[name])
        if n:
            entries[name] = game[name]
            done[name] = n
        else:
            other.append(name)
    return done, other


def migrated_only(old: bytes, game: dict[str, bytes] | None) -> tuple[bytes, dict[str, int], list[str]]:
    """The live package with only the game's migrations put in (the baseline the compile check judges first)."""
    entries = read_zip(old)
    done, other = migrate(entries, game)
    return (write_zip(entries) if done else old), done, other


def already_wired(entries: dict[str, bytes], url: str, version_world: str | None = None) -> bool:
    """The package already has this brain's address wired in."""
    if TARGET not in entries:
        return False
    v = wired_values(entries[TARGET])
    return v.get("Url") == url and (version_world is None or v.get("World") == version_world)
