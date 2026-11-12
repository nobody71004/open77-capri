#!/usr/bin/env bash
# Sets up the PRODUCTION Mass Override gate beside the staging one:
#   /opt/open77-mass-override  (the same gate.js + dev-server.js as staging)
#   systemd open77-mass-override.service on 127.0.0.1:11901
#   nginx location /mass-override/ on xyberrp.duckdns.org (staging keeps /mass-override-staging/)
# Idempotent: nothing that already exists is overwritten; nginx is backed up to /root
# first and restored if `nginx -t` fails.
set -euo pipefail
STAGE=/opt/open77-mass-override-staging
PROD=/opt/open77-mass-override
SITE=/etc/nginx/sites-enabled/xyberrp.duckdns.org
UNIT=/etc/systemd/system/open77-mass-override.service
TS=$(date -u +%Y%m%dT%H%M%SZ)

if ss -ltn | grep -q '127.0.0.1:11901 ' && ! systemctl is-active --quiet open77-mass-override; then
  echo "port 11901 is taken by something else"; exit 1
fi
mkdir -p "$PROD"
for f in gate.js dev-server.js; do
  [ -f "$PROD/$f" ] || cp "$STAGE/$f" "$PROD/$f"
done
sha256sum "$STAGE/gate.js" "$PROD/gate.js" "$STAGE/dev-server.js" "$PROD/dev-server.js" | cut -c1-16,65-

if [ ! -f "$UNIT" ]; then
cat > "$UNIT" <<EOF
[Unit]
Description=Open77 Mass Override feed (production)
After=network.target

[Service]
WorkingDirectory=$PROD
ExecStart=/usr/bin/node $PROD/dev-server.js
Environment=MASS_OVERRIDE_PORT=11901
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF
fi
systemctl daemon-reload
systemctl enable --now open77-mass-override >/dev/null 2>&1
sleep 1
echo "service: $(systemctl is-active open77-mass-override)"
echo "local feed: $(curl -s 'http://127.0.0.1:11901/feed?since=0')"

if ! grep -q 'location /mass-override/ ' "$SITE"; then
  cp "$SITE" "/root/xyberrp.duckdns.org.bak-mass-override-prod-$TS"
  python3 - "$SITE" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
out, done = [], False
for line in lines:
    out.append(line)
    if not done and "location /mass-override-staging/" in line:
        out.append(line.replace("location /mass-override-staging/", "location /mass-override/").replace("127.0.0.1:11900", "127.0.0.1:11901"))
        done = True
assert done, "staging location not found"
open(p, "w").write("\n".join(out))
PY
  if ! nginx -t 2>/dev/null; then
    cp "/root/xyberrp.duckdns.org.bak-mass-override-prod-$TS" "$SITE"
    echo "nginx -t failed; site restored"; exit 1
  fi
  systemctl reload nginx
  echo "nginx: /mass-override/ added (backup /root/xyberrp.duckdns.org.bak-mass-override-prod-$TS)"
fi
grep -n "mass-override" "$SITE" | cut -c1-120
sleep 1
echo "public production feed: $(curl -s 'https://xyberrp.duckdns.org/mass-override/feed?since=0')"
echo "public staging feed:    $(curl -s 'https://xyberrp.duckdns.org/mass-override-staging/feed?since=0')"
echo GATE-READY
