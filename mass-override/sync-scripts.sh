#!/usr/bin/env bash
# Installs the Mass Override scripts into a Cyberpunk 2077 install and checks the
# edits they depend on.
#
# The compile errors on the server came from shipping Capri.MassOverride.reds
# alone: it calls CapriSystem.MassOverrideShown() and reads
# CapriStorage.massOverrideLastAt, and both live in files that were not updated.
# This script copies the two files it owns and refuses to finish quietly when the
# other three pieces are missing.
#
# Usage: ./sync-scripts.sh "/path/to/Cyberpunk 2077"
set -euo pipefail

GAME="${1:-}"
if [ -z "$GAME" ]; then
  echo "usage: $0 \"/path/to/Cyberpunk 2077\"" >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../game/r6/scripts"
CAPRI="$GAME/r6/scripts/CapriPersonalityConstruct"

if [ ! -d "$CAPRI" ]; then
  echo "not a Cyberpunk 2077 install: $CAPRI is missing" >&2
  exit 2
fi

mkdir -p "$GAME/r6/scripts/Open77"
cp "$SRC/Open77/Open77MassOverride.reds" "$GAME/r6/scripts/Open77/"
cp "$SRC/CapriPersonalityConstruct/Capri.MassOverride.reds" "$CAPRI/"
echo "copied Open77MassOverride.reds and Capri.MassOverride.reds"

status=0
check() {
  if grep -q "$2" "$1"; then
    echo "ok      $(basename "$1"): $3"
  else
    echo "MISSING $(basename "$1"): $3" >&2
    status=1
  fi
}

check "$CAPRI/Capri.System.reds"  "func MassOverrideShown"  "public func MassOverrideShown() -> Bool { return this.m_presence.Shown(); }"
check "$CAPRI/Capri.Storage.reds" "massOverrideLastAt"     "public let massOverrideLastAt: Float;"
check "$CAPRI/Capri.Actions.reds" 'case "mass_override"'   'case "mass_override": return CapriMassOverride.Run(player, CapriSystem.Get(player.GetGame()));'

if [ "$status" -ne 0 ]; then
  echo >&2
  echo "The scripts above are out of date. Mass Override will not compile until" >&2
  echo "they are updated; see docs/MASS_OVERRIDE.md, \"Deploying the scripts\"." >&2
  exit 1
fi

echo "all dependencies present"
