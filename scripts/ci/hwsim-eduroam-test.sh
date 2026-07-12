#!/bin/bash
# In-guest eduroam test (run as root via ssh). Stands up a fake "eduroam" AP
# with a real WPA2-Enterprise EAP server (PEAP/MSCHAPv2) on one mac80211_hwsim
# radio, then lets the system's own lisa-wifi-setup service connect on the
# other. Credentials come from EDUROAM_IDENTITY / EDUROAM_PASSWORD env vars.
set -euo pipefail

: "${EDUROAM_IDENTITY:?}" "${EDUROAM_PASSWORD:?}"

echo "== reset any previous attempt =="
pkill hostapd 2>/dev/null || true
systemctl stop 'netplan-wpa-*.service' 2>/dev/null || true
rm -f /etc/netplan/70-lisa-wifi.yaml
rmmod mac80211_hwsim 2>/dev/null || true

echo "== harness tools =="
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq hostapd iw > /dev/null
systemctl stop hostapd 2>/dev/null || true

echo "== load virtual radios =="
modprobe mac80211_hwsim radios=2
sleep 2

echo "== rename AP radio to zap0 (sorts after wl*, so the detector ignores it) =="
AP_SRC=$(iw dev | awk '$1=="Interface"{print $2}' | sort | head -1)
ip link set "$AP_SRC" down
ip link set "$AP_SRC" name zap0

echo "== EAP server cert =="
mkdir -p /etc/lisa-test
openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
  -keyout /etc/lisa-test/server.key -out /etc/lisa-test/server.crt \
  -subj "/CN=radius.test.local" 2>/dev/null

echo "== hostapd: WPA2-Enterprise AP with builtin EAP server =="
cat > /etc/lisa-test/eap_users <<EOF
* PEAP
"$EDUROAM_IDENTITY" MSCHAPV2 "$EDUROAM_PASSWORD" [2]
EOF
cat > /etc/lisa-test/hostapd.conf <<EOF
interface=zap0
driver=nl80211
ssid=eduroam
hw_mode=g
channel=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-EAP
rsn_pairwise=CCMP
ieee8021x=1
eap_server=1
eap_user_file=/etc/lisa-test/eap_users
ca_cert=/etc/lisa-test/server.crt
server_cert=/etc/lisa-test/server.crt
private_key=/etc/lisa-test/server.key
EOF
hostapd -B /etc/lisa-test/hostapd.conf

echo "== DHCP server on the AP side (networkd) =="
mkdir -p /run/systemd/network
cat > /run/systemd/network/50-zap0.network <<'EOF'
[Match]
Name=zap0
[Network]
Address=10.99.0.1/24
DHCPServer=yes
EOF
systemctl restart systemd-networkd
sleep 3

echo "== run the SHIPPED wifi setup script =="
/usr/local/sbin/lisa-wifi-setup

echo "== wait for association + DHCP =="
CLIENT=$(iw dev | awk '$1=="Interface"{print $2}' | grep '^wl' | head -1)
ok=0
for i in $(seq 1 30); do
  if ip -4 addr show "$CLIENT" 2>/dev/null | grep -q 'inet 10\.99\.0\.'; then ok=1; break; fi
  sleep 2
done

echo "===== RESULTS ====="
iw dev "$CLIENT" link
ip -4 addr show "$CLIENT" | grep inet || true
wpa_state=$(wpa_cli -i "$CLIENT" status 2>/dev/null | awk -F= '$1=="wpa_state"{print $2}')
journalctl --no-pager -n 300 | grep -iE 'CTRL-EVENT-EAP-SUCCESS|CTRL-EVENT-CONNECTED' | tail -3

if [ "$ok" = 1 ] && [ "$wpa_state" = "COMPLETED" ]; then
  echo "HWSIM-EDUROAM: PASS"
else
  echo "HWSIM-EDUROAM: FAIL (ok=$ok wpa_state=$wpa_state)"
  journalctl --no-pager -n 100 | grep -i 'wpa_supplicant\|hostapd' | tail -20
  exit 1
fi
