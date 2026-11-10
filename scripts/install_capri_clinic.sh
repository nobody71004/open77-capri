#!/usr/bin/env bash
# Install the Capri Personality Construct OS chip into one Open77 resource root.
# This intentionally does not edit server.jsonc and does not enable unsecured.
set -Eeuo pipefail

ROOT="${OPEN77_ROOT:-/opt/open77-xbuniverse}"
SERVICE="${OPEN77_SERVICE:-open77-xbuniverse.service}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PATCHER="${PATCHER:-${SCRIPT_DIR}/patch_capri_clinic.py}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This installer must run as root." >&2
  exit 1
fi
if [[ ! -f "${PATCHER}" ]]; then
  echo "Missing patcher: ${PATCHER}" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (3.10 or newer)." >&2
  exit 1
fi

for rel in \
  resources/opx_infinity/config/ripperdoc.lua \
  resources/opx_infinity/modules/ripperdoc/module.lua \
  resources/opx_infinity/modules/ripperdoc/locales.lua; do
  if [[ ! -f "${ROOT}/${rel}" ]]; then
    echo "Missing ${ROOT}/${rel}" >&2
    exit 1
  fi
done

echo "==> Patching Capri clinic chip in ${ROOT}"
python3 "${PATCHER}" --root "${ROOT}" --apply

echo "==> Restarting ${SERVICE}"
systemctl restart "${SERVICE}"
for _ in $(seq 1 30); do
  if systemctl is-active --quiet "${SERVICE}"; then
    break
  fi
  sleep 2
done
if ! systemctl is-active --quiet "${SERVICE}"; then
  echo "ERROR: ${SERVICE} did not become active." >&2
  systemctl status --no-pager -l "${SERVICE}" | tail -80 >&2 || true
  exit 1
fi

echo "Capri clinic chip installed; ${SERVICE} is active."
echo "Run scripts/verify_capri_clinic.sh for the file and service checks."
