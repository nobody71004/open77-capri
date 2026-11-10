#!/usr/bin/env python3
"""Add the Capri Personality Construct OS chip to one Open77 resource root.

The patch is deliberately split into three edits:
  * one CATALOG entry in config/ripperdoc.lua;
  * an explicit RP_SOLD opt-in in module.lua's Unsold policy;
  * EN/FR name, grade and description keys in locales.lua.

It never edits the server.jsonc.  Run with --out for a dry run, or --apply as
root to write in place after creating .before-capri-chip backups.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

ENTRY_ID = "capri_personality_construct"
NAME_KEY = "ripperdoc.item.capri"
GRADE_KEY = "ripperdoc.grade.capri.prototype"
DESC_KEY = "ripperdoc.cw.capri_personality_construct.desc"

ENTRY = """\t\t{
\t\t\t-- Capri Personality Construct: a forbidden Arasaka chip.
\t\t\t-- The Capri client package supplies her mind and voice; the
\t\t\t-- clinic owns the OS slot, the price, the capacity and the ledger.
\t\t\tid = 'capri_personality_construct',
\t\t\tNAME = 'ripperdoc.item.capri',
\t\t\tDESC = 'ripperdoc.cw.capri_personality_construct.desc',
\t\t\tICON = 'cw_cyberdeck_arasaka',
\t\t\tSYSTEM = 'operating_system', KIND = 'rp', TIER = 4, CAPACITY = 16,
\t\t\tSLOT = 'operating_system',
\t\t\tRP_SOLD = true,
\t\t\tREMOVE = 250,
\t\t\tWEAR = 2,
\t\t\tGRADES = {
\t\t\t\t{ id = 'prototype', NAME = 'ripperdoc.grade.capri.prototype', PRICE = 2500 },
\t\t\t},
\t\t},
"""

LOCALE = {
    "en": {
        "name": "Capri Personality Construct",
        "grade": "Prototype",
        "desc": "A forbidden Arasaka construct on a single chip. Fits the Operating System slot; the Capri client supplies her mind and voice. No combat stats.",
    },
    "fr": {
        "name": "Construction de personnalité Capri",
        "grade": "Prototype",
        "desc": "Une construction Arasaka interdite sur une puce. Occupe l'emplacement Système d'exploitation ; le client Capri fournit son esprit et sa voix. Aucun bonus de combat.",
    },
}


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_matching_brace(text: str, start: int) -> int:
    """Return the index of the brace matching text[start] == '{'."""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "-" and text.startswith("--", i):
            end = text.find("\n", i + 2)
            i = len(text) if end < 0 else end + 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces while locating CATALOG")


def patch_config(text: str) -> str:
    if f"id = '{ENTRY_ID}'" in text:
        return text
    match = re.search(r"(?m)^\s*CATALOG\s*=\s*\{", text)
    if not match:
        raise ValueError("CATALOG = { not found")
    open_brace = text.find("{", match.start())
    close_brace = find_matching_brace(text, open_brace)
    line_start = text.rfind("\n", 0, close_brace) + 1
    if line_start <= 0:
        raise ValueError("could not locate CATALOG closing line")
    return text[:line_start] + ENTRY + text[line_start:]


def patch_module(text: str) -> str:
    marker = "\tif type(entry) ~= 'table' or entry.KIND ~= 'rp' then return false end"
    if "entry.RP_SOLD == true" in text:
        return text
    if text.count(marker) != 1:
        raise ValueError(f"expected exactly one Unsold rp guard, found {text.count(marker)}")
    replacement = marker + "\n\tif entry.RP_SOLD == true then return false end"
    return text.replace(marker, replacement, 1)


def lua_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def patch_locales(text: str) -> str:
    if f"['{NAME_KEY}']" in text:
        return text
    lines = text.splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines) if re.match(r"\s*\['ripperdoc\.item\.deck'\]\s*=", line)]
    if len(anchors) != 2:
        raise ValueError(f"expected two ripperdoc.item.deck anchors, found {len(anchors)}")
    # Insert from the bottom so the earlier anchor index remains valid.
    for lang, index in zip(("fr", "en"), reversed(anchors)):
        data = LOCALE[lang]
        addition = (
            f"\t['{NAME_KEY}'] = {lua_string(data['name'])},\n"
            f"\t['{GRADE_KEY}'] = {lua_string(data['grade'])},\n"
            f"\t['{DESC_KEY}'] = {lua_string(data['desc'])},\n"
        )
        lines.insert(index + 1, addition)
    return "".join(lines)


def check_balanced(text: str, label: str) -> None:
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "-" and text.startswith("--", i):
            end = text.find("\n", i + 2)
            i = len(text) if end < 0 else end + 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
            if depth < 0:
                raise ValueError(f"{label}: closing bracket without opener at byte {i}")
        i += 1
    if depth != 0:
        raise ValueError(f"{label}: {depth} unmatched opener(s)")


def patch_root(source: Path, destination: Path | None, apply: bool) -> None:
    files = {
        "config": source / "resources/opx_infinity/config/ripperdoc.lua",
        "module": source / "resources/opx_infinity/modules/ripperdoc/module.lua",
        "locales": source / "resources/opx_infinity/modules/ripperdoc/locales.lua",
    }
    for name, path in files.items():
        if not path.is_file():
            raise FileNotFoundError(path)
    original = {name: read_text(path) for name, path in files.items()}
    patched = {
        "config": patch_config(original["config"]),
        "module": patch_module(original["module"]),
        "locales": patch_locales(original["locales"]),
    }
    for name, text in patched.items():
        check_balanced(text, name)
    if f"id = '{ENTRY_ID}'" not in patched["config"]:
        raise ValueError("entry missing after config patch")
    if "entry.RP_SOLD == true" not in patched["module"]:
        raise ValueError("RP_SOLD opt-in missing after module patch")
    if patched["locales"].count(f"['{NAME_KEY}']") != 2:
        raise ValueError("Capri locale keys were not added to both languages")

    if apply:
        if os.geteuid() != 0:
            raise PermissionError("--apply must run as root")
        for name, path in files.items():
            backup = path.with_name(path.name + ".before-capri-chip")
            if not backup.exists():
                shutil.copy2(path, backup)
            if read_text(path) != patched[name]:
                write_text(path, patched[name])
            print(f"applied {path}")
            print(f"  sha256 {sha256(path)}")
    elif destination is not None:
        for name, path in files.items():
            out = destination / path.relative_to(source)
            out.parent.mkdir(parents=True, exist_ok=True)
            write_text(out, patched[name])
            print(f"wrote {out}")
            print(f"  sha256 {sha256(out)}")
    else:
        raise ValueError("one of --apply or --out is required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path, help="server root, e.g. /opt/open77-xbuniverse")
    parser.add_argument("--out", type=Path, help="write patched copies here instead of in place")
    parser.add_argument("--apply", action="store_true", help="write in place as root")
    args = parser.parse_args()
    if args.apply and args.out:
        parser.error("--apply and --out are mutually exclusive")
    patch_root(args.root, args.out, args.apply)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
