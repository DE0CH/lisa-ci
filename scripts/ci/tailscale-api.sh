#!/bin/bash
# Tailscale API helpers for the final-ISO test (CI cannot ssh into the final
# image, so the tailnet join is verified externally and cleaned up afterwards).
#
#   tailscale-api.sh wait-join <since-epoch>    poll until a lisa* device
#                                               created after <since> appears
#   tailscale-api.sh cleanup <since-epoch>      delete all lisa* devices
#                                               created after <since>
# Env: TS_API_TOKEN
set -euo pipefail

: "${TS_API_TOKEN:?}"
API=https://api.tailscale.com/api/v2

list_ci_nodes() { # $1 = since epoch; prints "id hostname created" per line
  curl -fsS -u "$TS_API_TOKEN:" "$API/tailnet/-/devices" |
    jq -r --argjson since "$1" '
      .devices[]
      | select(.hostname | startswith("lisa"))
      | select((.created | fromdateiso8601) >= $since)
      | "\(.id) \(.hostname) \(.created)"'
}

case "$1" in
  wait-join)
    SINCE="${2:?since epoch}"
    echo "waiting up to 10 min for a lisa* device created after $(date -u -d @"$SINCE" 2>/dev/null || echo "$SINCE")"
    for i in $(seq 1 60); do
      nodes=$(list_ci_nodes "$SINCE")
      if [ -n "$nodes" ]; then
        echo "JOINED:"; echo "$nodes"
        exit 0
      fi
      sleep 10
    done
    echo "FAIL: no lisa* device appeared via API"
    exit 1
    ;;
  cleanup)
    SINCE="${2:?since epoch}"
    nodes=$(list_ci_nodes "$SINCE" || true)
    if [ -z "$nodes" ]; then echo "no CI nodes to clean up"; exit 0; fi
    while read -r id host created; do
      echo "deleting CI node $host ($id, created $created)"
      curl -fsS -X DELETE -u "$TS_API_TOKEN:" "$API/device/$id" || echo "delete failed for $id"
    done <<< "$nodes"
    ;;
  *)
    echo "usage: tailscale-api.sh wait-join|cleanup <since-epoch>"; exit 2
    ;;
esac
