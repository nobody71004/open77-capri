#!/bin/bash
set -Eeuo pipefail

ROOT=/opt/open77-xbuniverse-staging
OLD_SHA=263c85dfdde6de37d94068a905e4514221c7457ed82a8e98ab8d47cec46ab244
OLD_SIZE=26191281

echo "== identity =="
id

echo "== Capri package by name =="
find "$ROOT" /var/lib /srv -xdev -type f -iname '*CapriPersonalityConstruct*.zip' -printf '%s %u:%g %TY-%Tm-%TdT%TH:%TM %p\n' 2>/dev/null | head -40 || true

echo "== Capri package by exact old size =="
find "$ROOT" /var/lib /srv -xdev -type f -size ${OLD_SIZE}c -printf '%s %u:%g %TY-%Tm-%TdT%TH:%TM %p\n' 2>/dev/null | head -40 || true

echo "== exact hash candidates =="
while IFS= read -r f; do
  h=$(sha256sum "$f" | awk '{print $1}')
  if [ "$h" = "$OLD_SHA" ]; then printf '%s %s\n' "$h" "$f"; fi
done < <(find "$ROOT" /var/lib /srv -xdev -type f -size ${OLD_SIZE}c 2>/dev/null)

echo "== resources layout =="
find "$ROOT/resources" -maxdepth 3 -printf '%y %s %u:%g %p\n' 2>/dev/null | head -120 || true

echo "== .open77 layout =="
find "$ROOT/.open77" -maxdepth 3 -printf '%y %s %u:%g %p\n' 2>/dev/null | head -120 || true

echo "== Capri sidecar refs =="
grep -RIn --exclude='*.zip' --exclude='*.archive' -m 3 'CapriPersonalityConstruct-1.16-preflightfix' "$ROOT" 2>/dev/null | head -40 || true

echo "== service status =="
systemctl is-active open77-xbuniverse-staging || true
