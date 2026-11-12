#!/usr/bin/env bash
# Exercises the public routes of both gates the way the game does (feed poll and a
# report), and shows that each report reached its own gate. The report is marked
# phase "deploy-check" so it cannot be mistaken for a cast.
set -euo pipefail
for base in mass-override mass-override-staging; do
  feed=$(curl -s "https://xyberrp.duckdns.org/$base/feed?since=0")
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'content-type: application/json' \
    -d "{\"phase\":\"deploy-check\",\"gate\":\"$base\",\"build\":\"1.16.15\"}" "https://xyberrp.duckdns.org/$base/report")
  echo "$base: feed='$feed' report=$code"
done
sleep 1
echo "production gate log: $(journalctl -u open77-mass-override --since '-2 min' --no-pager -o cat | grep deploy-check | tail -1)"
echo "staging gate log:    $(journalctl -u open77-mass-override-staging --since '-2 min' --no-pager -o cat | grep deploy-check | tail -1)"
