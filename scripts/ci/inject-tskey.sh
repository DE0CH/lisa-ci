#!/bin/bash
# Inject the CI tailscale key into the booted test VM. The test ISO is always
# built with a dummy key so no artifact ever contains a real credential; the
# real key exists only in CI and enters the guest over SSH at test time. The
# join service re-reads /etc/lisa-tskey on each attempt, so a restart makes it
# pick up the injected key immediately.
set -euo pipefail
: "${CONSOLE_PASSWORD:?}"
KEY="${TS_AUTHKEY_TEST:-}"
case "$KEY" in
  tskey-auth-*) ;;
  *) echo "dummy/absent CI tailscale key - skipping injection (join stays retry-pending)"; exit 0 ;;
esac
{ echo "$CONSOLE_PASSWORD"; printf '%s' "$KEY"; } | \
  timeout 30 ssh -i test_key -p 2222 -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=known_hosts_vm -o BatchMode=yes deyao@127.0.0.1 \
    "sudo -S -p '' bash -c 'umask 077; cat > /etc/lisa-tskey && systemctl restart --no-block lisa-tailscale-join.service && echo key-injected'"
