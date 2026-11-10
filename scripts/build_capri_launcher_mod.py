#!/usr/bin/env python3
"""Build the Open77 Launcher archive for Capri: Personality Construct.

The launcher installs a server's required mods when the player connects. A
required mod is one zip whose entries are game-root paths, for example
``archive/pc/mod/CapriPersonalityConstruct.archive``. This script takes the
official Capri release (as downloaded from its author) and produces that zip,
plus the SHA-256 and size the server's ``requiredMods`` entry must pin.

It never downloads anything and never ships third-party files itself. Point it
at a release you already have and, optionally, at the five Codeware scripts
from your game install so the package matches the Open77 package split.

Example (Windows):

    python scripts/build_capri_launcher_mod.py ^
      --capri-zip "C:\\Users\\me\\Downloads\\CapriPersonalityConstruct 1.16.zip" ^
      --codeware-scripts "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Cyberpunk 2077\\r6\\scripts\\CapriPersonalityConstruct\\Codeware" ^
      --version 1.16.1 ^
      --out-dir dist

Example (Linux):

    python3 scripts/build_capri_launcher_mod.py \
      --capri-zip /tmp/CapriPersonalityConstruct-1.16.zip \
      --codeware-scripts /opt/game/r6/scripts/CapriPersonalityConstruct/Codeware \
      --version 1.16.1 --out-dir dist
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

# Must match Open77.Launcher/ModStack/ModRootPolicy.Roots and the server's twin.
MOD_ROOTS = (
    "bin/x64/plugins/cyber_engine_tweaks/mods",
    "red4ext/plugins",
    "bin/x64/plugins",
    "archive/pc/mod",
    "r6/scripts",
    "r6/tweaks",
    "r6/input",
    "r6/config",
    "engine/config",
    "engine/tools",
    "EasyAntiCheat",
    "mods",
    "bin/x64",
)

CET_MODS_ROOT = "bin/x64/plugins/cyber_engine_tweaks/mods"
CAPRI_VOZ_READY_FILE = CET_MODS_ROOT + "/CapriVozReady/init.lua"
CAPRI_VOZ_READY_SOURCE = Path(__file__).resolve().parents[1] / "client" / "cet" / "CapriVozReady" / "init.lua"

# The player package must not carry any CET UI. CapriPersonalityConstruct's
# CET mod is the F1 chat/settings window; it is stripped even when the official
# release includes it. Only the no-UI CapriVozReady heartbeat is kept.
REQUIRED_FILES = (
    "archive/pc/mod/CapriPersonalityConstruct.archive",
    "red4ext/plugins/CapriPersonalityConstruct/CapriPersonalityConstruct.dll",
    CAPRI_VOZ_READY_FILE,
)

CODEWARE_DIR = "r6/scripts/CapriPersonalityConstruct/Codeware"
CODEWARE_COUNT = 5
DISPLAY_NAME = "Capri - AI Companion with Voice (LLM)"
MOD_ID = "capri-personality-construct"

# A fixed timestamp makes the archive reproducible: the same inputs always
# produce the same SHA-256, so staging and production can share one blob.
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


class BuildError(SystemExit):
    pass


def normalize(name: str) -> str:
    path = name.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.strip("/")


def root_of(path: str) -> str | None:
    for root in MOD_ROOTS:
        if path == root or path.startswith(root + "/"):
            return root
    return None


def is_traversal(path: str) -> bool:
    if not path or path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return True
    return any(part in ("", ".", "..") for part in PurePosixPath(path).parts)


def refusal_reason(path: str) -> str | None:
    """Return why a path may not travel to a player, or None when it may."""
    if is_traversal(path):
        return "path traversal or absolute path"
    if root_of(path) is None:
        return "outside every Open77 mod root"
    lower = path.lower()
    if lower.startswith("r6/storages/"):
        return "player storage (settings, keys, saves)"
    if "/cache/" in lower or lower.startswith("red4ext/plugins/capripersonalityconstruct/caprivoz/cache/"):
        return "generated voice cache"
    if lower.endswith("/config.json") and "/caprivoz/" in lower:
        return "per-user CapriVoz configuration (local paths and keys)"
    if lower.endswith((".log", "db.sqlite3")) or ".before-" in lower:
        return "local runtime state"
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_zip(path: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalize(info.filename)
            if not name:
                continue
            reason = refusal_reason(name)
            if reason is not None:
                raise BuildError(f"refusing {info.filename!r}: {reason}")
            if name in entries:
                raise BuildError(f"duplicate entry in {path}: {name}")
            entries[name] = archive.read(info)
    return entries


def strip_cet_ui(entries: dict[str, bytes]) -> list[str]:
    """Remove every CET mod except the no-UI CapriVozReady backend.

    The launcher package is player-facing. CET mods draw their own windows and
    hotkeys, so none of them belongs in this package: not Capri's F1 window and
    not the admin-only CapriMcpBridge. CapriVozReady is kept because it has no
    draw handler and only calls Capri's public voice health check.
    """
    removed = []
    for name in list(entries):
        if name.startswith(CET_MODS_ROOT + "/") and name != CAPRI_VOZ_READY_FILE:
            removed.append(name)
            del entries[name]
    return sorted(removed)


def write_zip(entries: dict[str, bytes], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name])
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capri-zip", required=True, type=Path, help="official Capri release zip")
    parser.add_argument(
        "--codeware-scripts",
        type=Path,
        help="the five r6/scripts/Codeware/*.reds files from the game install",
    )
    parser.add_argument("--version", default="1.16.1", help="version the server will pin")
    parser.add_argument("--out-dir", default="dist", type=Path, help="where to write the launcher archive")
    parser.add_argument("--name", default=None, help="archive file name (default CapriPersonalityConstruct-<version>.zip)")
    args = parser.parse_args()

    if not args.capri_zip.is_file():
        raise BuildError(f"Capri release not found: {args.capri_zip}")

    entries = read_zip(args.capri_zip)
    removed_cet = strip_cet_ui(entries)
    if removed_cet:
        print(f"CET UI disabled: removed {len(removed_cet)} player-facing CET file(s)")
        for name in removed_cet:
            print(f"  - {name}")
    else:
        print("CET UI disabled: no CET files were present in the official release")

    if not CAPRI_VOZ_READY_SOURCE.is_file():
        raise BuildError(f"CapriVozReady resource not found: {CAPRI_VOZ_READY_SOURCE}")
    entries[CAPRI_VOZ_READY_FILE] = CAPRI_VOZ_READY_SOURCE.read_bytes()
    print(f"CapriVozReady resource: added {CAPRI_VOZ_READY_FILE}")
    cet_files = sorted(name for name in entries if name.startswith(CET_MODS_ROOT + "/"))
    if cet_files != [CAPRI_VOZ_READY_FILE]:
        raise BuildError(
            "player package must carry only the CapriVozReady CET backend; found "
            + ", ".join(cet_files)
        )
    missing = [name for name in REQUIRED_FILES if name not in entries]
    if missing:
        raise BuildError("Capri release is missing " + ", ".join(missing))
    if not any(
        name.startswith("r6/scripts/CapriPersonalityConstruct/") and name.endswith(".reds")
        for name in entries
    ):
        raise BuildError("Capri release has no r6/scripts/CapriPersonalityConstruct/*.reds files")

    if args.codeware_scripts is not None:
        if not args.codeware_scripts.is_dir():
            raise BuildError(f"Codeware scripts folder not found: {args.codeware_scripts}")
        scripts = sorted(
            path for path in args.codeware_scripts.iterdir()
            if path.is_file() and path.suffix.lower() == ".reds"
        )
        if len(scripts) != CODEWARE_COUNT:
            raise BuildError(
                f"expected {CODEWARE_COUNT} Codeware .reds files in {args.codeware_scripts}, "
                f"found {len(scripts)}"
            )
        for script in scripts:
            target = f"{CODEWARE_DIR}/{script.name}"
            if target in entries:
                raise BuildError(f"Capri release already contains {target}")
            entries[target] = script.read_bytes()
        print(f"Codeware dependencies: added {CODEWARE_COUNT} scripts under {CODEWARE_DIR}/")
    else:
        print("Codeware dependencies: not supplied; the package will rely on the installed Codeware package")

    file_name = args.name or f"CapriPersonalityConstruct-{args.version}.zip"
    out_dir = args.out_dir
    archive_path = out_dir / file_name
    write_zip(entries, archive_path)

    sha = sha256_file(archive_path)
    size = archive_path.stat().st_size
    file_count = len(entries)
    roots = sorted({root_of(name) for name in entries if root_of(name)})
    metadata = {
        "id": MOD_ID,
        "version": args.version,
        "displayName": DISPLAY_NAME,
        "fileName": file_name,
        "sha256": sha,
        "sizeBytes": size,
        "capability": "executable",
        "fileCount": file_count,
        "roots": roots,
        "importedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    (out_dir / f"{sha}.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    required_mod = {
        "id": MOD_ID,
        "source": "hosted",
        "displayName": DISPLAY_NAME,
        "version": args.version,
        "sha256": sha,
        "sizeBytes": size,
    }
    print()
    print(f"archive : {archive_path}")
    print(f"files   : {file_count}")
    print(f"sha256  : {sha}")
    print(f"size    : {size}")
    print(f"roots   : {', '.join(roots)}")
    print()
    print("server.jsonc requiredMods.packages entry:")
    print(json.dumps(required_mod, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
