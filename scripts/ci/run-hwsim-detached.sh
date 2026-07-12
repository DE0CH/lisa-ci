#!/bin/bash
# Run the in-guest eduroam test detached via systemd-run and poll for the
# verdict. Detached because the test triggers `netplan apply`, which can drop
# the very SSH session that launched it.
set -euo pipefail
: "${CONSOLE_PASSWORD:?}" "${EDUROAM_IDENTITY:?}" "${EDUROAM_PASSWORD:?}"

SSH=(ssh -i test_key -p 2222 -o StrictHostKeyChecking=accept-new
     -o UserKnownHostsFile=known_hosts_vm -o BatchMode=yes -o ConnectTimeout=8
     -o ServerAliveInterval=5 -o ServerAliveCountMax=3 deyao@127.0.0.1)

echo "== upload test script =="
{ printf 'export EDUROAM_IDENTITY=%q\nexport EDUROAM_PASSWORD=%q\n' \
    "$EDUROAM_IDENTITY" "$EDUROAM_PASSWORD"
  cat scripts/ci/hwsim-eduroam-test.sh
} | timeout 30 "${SSH[@]}" 'cat > /tmp/hwsim-test.sh'

echo "== launch detached =="
echo "$CONSOLE_PASSWORD" | timeout 30 "${SSH[@]}" \
  "sudo -S -p '' systemd-run --no-block --unit=lisa-hwsim-test bash /tmp/hwsim-test.sh"

echo "== poll for verdict =="
verdict=""
for i in $(seq 1 60); do
  verdict=$(echo "$CONSOLE_PASSWORD" | timeout 25 "${SSH[@]}" \
    "sudo -S -p '' journalctl -u lisa-hwsim-test --no-pager 2>/dev/null | grep -oE 'HWSIM-EDUROAM: (PASS|FAIL).*' | tail -1" \
    2>/dev/null) || true
  [ -n "$verdict" ] && break
  sleep 5
done

echo "== full test log =="
echo "$CONSOLE_PASSWORD" | timeout 40 "${SSH[@]}" \
  "sudo -S -p '' journalctl -u lisa-hwsim-test --no-pager | tail -80" || true

echo "verdict: ${verdict:-NONE (timed out)}"
case "$verdict" in
  *PASS*) exit 0 ;;
  *) exit 1 ;;
esac
