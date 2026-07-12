#!/bin/bash
# In-guest verification (run as root via ssh). Usage: verify-system.sh <n-keys>
# Checks identity, SSH posture, offline deb install, wifi payload, tailnet join.
set -uo pipefail

EXPECT_KEYS="${1:?expected authorized_keys count}"
EXPECT_TS="${2:-1}"   # 0 when the build used a dummy tailscale key (public repo)
fail=0

# Settle first: timezone/runcmd are cloud-init stages that finish after sshd
# is already accepting connections.
echo "-- waiting for cloud-init to finish (up to 300s) --"
timeout 300 cloud-init status --wait || echo "warn: cloud-init still running or errored"
chk() { # chk <name> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "PASS: $1 = $2"
  else echo "FAIL: $1 expected [$2] got [$3]"; fail=1; fi
}

chk hostname lisa "$(hostname)"
chk timezone Asia/Hong_Kong "$(timedatectl show -p Timezone --value)"
chk authorized_keys_count "$EXPECT_KEYS" "$(grep -c ssh- /home/deyao/.ssh/authorized_keys)"
chk de0ch_key_present 1 "$(grep -c 'GJ9quHj1tvkeftOu' /home/deyao/.ssh/authorized_keys)"

chk sshd_password_auth no "$(sshd -T | awk '$1=="passwordauthentication"{print $2}')"
chk sshd_kbdint_auth no "$(sshd -T | awk '$1=="kbdinteractiveauthentication"{print $2}')"

chk wpasupplicant_installed 1 "$(dpkg-query -W -f='${db:Status-Status}\n' wpasupplicant 2>/dev/null | grep -c installed)"
chk curl_installed 1 "$(dpkg-query -W -f='${db:Status-Status}\n' curl 2>/dev/null | grep -c installed)"
chk debs_installed_offline 1 "$(grep -c 'Dir::Etc::sourcelist=/dev/null.*lisa-debs' /var/log/apt/history.log)"

chk wifi_setup_enabled enabled "$(systemctl is-enabled lisa-wifi-setup.service)"
chk wifi_setup_script_mode 755 "$(stat -c %a /usr/local/sbin/lisa-wifi-setup)"
chk wifi_creds_in_script 1 "$(grep -c 'method: peap' /usr/local/sbin/lisa-wifi-setup)"

if [ "$EXPECT_TS" = 1 ]; then
  echo "-- waiting up to 120s for tailscale join --"
  ts_ip=""
  for i in $(seq 1 24); do
    ts_ip=$(tailscale ip -4 2>/dev/null | head -1) && [ -n "$ts_ip" ] && break
    sleep 5
  done
  case "$ts_ip" in
    100.*) echo "PASS: tailscale joined ($ts_ip)";;
    *) echo "FAIL: tailscale did not join (ip=[$ts_ip])"
       journalctl -u lisa-tailscale-join --no-pager | tail -20; fail=1;;
  esac
  # The join script removes the key and disables itself moments after
  # `tailscale up` returns — poll for the settled end state, don't race it.
  echo "-- waiting up to 60s for join cleanup --"
  for i in $(seq 1 12); do
    [ ! -f /etc/lisa-tskey ] && [ "$(systemctl is-enabled lisa-tailscale-join.service)" = "disabled" ] && break
    sleep 5
  done
  chk tailscale_key_removed missing "$([ -f /etc/lisa-tskey ] && echo present || echo missing)"
  chk join_service_disabled disabled "$(systemctl is-enabled lisa-tailscale-join.service)"
else
  # Dummy key: the join must keep retrying across boots — key stays, unit stays
  # enabled. This is the correct behavior for a machine that can't reach its
  # tailnet yet, and it's what a dummy-credential (public repo) build asserts.
  echo "-- dummy tailscale key: asserting retry-pending state --"
  chk tailscale_key_kept present "$([ -f /etc/lisa-tskey ] && echo present || echo missing)"
  chk join_service_still_enabled enabled "$(systemctl is-enabled lisa-tailscale-join.service)"
fi

[ "$fail" -eq 0 ] && echo "VERIFY-SYSTEM: ALL PASS" || echo "VERIFY-SYSTEM: FAILURES"
exit "$fail"
