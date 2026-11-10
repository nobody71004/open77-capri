#!/usr/bin/env bash
# Installs the Mass Override scripts into a Cyberpunk 2077 install and checks the
# one line the action depends on.
#
# Earlier versions of Capri.MassOverride.reds called CapriSystem.MassOverrideShown()
# and read CapriStorage.massOverrideLastAt. Both needed matching edits in
# Capri.System.reds and Capri.Storage.reds, and when those edits were not synced the
# whole script set failed to compile. The action now references nothing outside the
# stock Capri build, so only these two files need copying.
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

# The dispatch cases are the only thing outside these two files. They live in Capri's
# own action switch, and both have to be there: the cast, and the live mode control
# that mirrors the dev server's /mode route.
check "$CAPRI/Capri.Actions.reds" 'case "mass_override":' \
  'case "mass_override": return CapriMassOverride.Run(player, CapriSystem.Get(player.GetGame()));'
check "$CAPRI/Capri.Actions.reds" 'case "mass_override_mode":' \
  'case "mass_override_mode": return CapriMassOverride.SetModeFromAction(target);'
check "$CAPRI/Capri.Actions.reds" 'mass_override_mode' \
  'the prompt line that lets Capri choose mass_override_mode'

if [ "$status" -ne 0 ]; then
  echo >&2
  echo "Capri has no mass_override action to reach. See docs/MASS_OVERRIDE.md." >&2
  exit 1
fi

echo "all dependencies present"
