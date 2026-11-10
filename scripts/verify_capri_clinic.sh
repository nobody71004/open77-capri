#!/usr/bin/env bash
# Verify the server-side Capri chip patch. Read-only; no root required.
set -Eeuo pipefail

ROOT="${OPEN77_ROOT:-/opt/open77-xbuniverse}"
SERVICE="${OPEN77_SERVICE:-open77-xbuniverse.service}"
CONFIG="${ROOT}/resources/opx_infinity/config/ripperdoc.lua"
MODULE="${ROOT}/resources/opx_infinity/modules/ripperdoc/module.lua"
LOCALES="${ROOT}/resources/opx_infinity/modules/ripperdoc/locales.lua"
failed=0

check_file() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    printf 'OK   file: %s\n' "${file}"
  else
    printf 'FAIL file: %s\n' "${file}"
    failed=1
  fi
}

check_grep() {
  local label="$1" file="$2" pattern="$3"
  if [[ -f "${file}" ]] && grep -Fq -- "${pattern}" "${file}"; then
    printf 'OK   %s\n' "${label}"
  else
    printf 'FAIL %s\n' "${label}"
    failed=1
  fi
}

check_file "${CONFIG}"
check_file "${MODULE}"
check_file "${LOCALES}"
check_grep "catalogue entry" "${CONFIG}" "id = 'capri_personality_construct'"
check_grep "OS slot" "${CONFIG}" "SLOT = 'operating_system'"
check_grep "RP_SOLD opt-in" "${MODULE}" "if entry.RP_SOLD == true then return false end"
check_grep "EN locale name" "${LOCALES}" "['ripperdoc.item.capri'] = 'Capri Personality Construct'"
check_grep "FR locale name" "${LOCALES}" "['ripperdoc.item.capri'] = 'Construction de personnalité Capri'"
check_grep "prototype grade" "${CONFIG}" "id = 'prototype'"

if systemctl is-active --quiet "${SERVICE}"; then
  printf 'OK   service active: %s\n' "${SERVICE}"
else
  printf 'FAIL service inactive: %s\n' "${SERVICE}"
  failed=1
fi

if [[ "${failed}" -ne 0 ]]; then
  echo "Verification failed." >&2
  exit 1
fi
echo "Capri clinic verification passed."
