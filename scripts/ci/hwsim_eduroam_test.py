#!/usr/bin/env python3
"""In-guest eduroam test (runs as root in the installed VM, launched detached
via systemd-run because it triggers `netplan apply`). Stands up a fake
"eduroam" AP with a real WPA2-Enterprise EAP server (PEAP/MSCHAPv2) on one
mac80211_hwsim radio, then lets the system's own lisa-wifi-setup service
connect on the other radio. Credentials from EDUROAM_USERNAME/EDUROAM_PASSWORD.
"""
import pathlib
import re
import subprocess
import sys
import time


def sh(cmd: str, check: bool = False) -> str:
    print(f"+ {cmd}", flush=True)
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    if check and r.returncode != 0:
        print(r.stdout + r.stderr, flush=True)
        sys.exit(f"command failed rc={r.returncode}: {cmd}")
    return r.stdout.strip()


def wifi_interfaces() -> list:
    return sorted(
        p.name for p in pathlib.Path("/sys/class/net").iterdir()
        if (p / "wireless").is_dir()
    )


def shipped_credentials() -> tuple:
    """Read the eduroam credentials out of the shipped Wi-Fi script, so the
    fake AP always matches whatever the ISO was built with (code-generated
    dummies for test builds — no secrets in the test path)."""
    text = pathlib.Path("/usr/local/sbin/lisa-wifi-setup").read_text()
    identity = re.search(r'identity: "([^"]+)"', text)
    password = re.search(r'password: "([^"]+)"', text)
    if not identity or not password:
        sys.exit("could not parse credentials from /usr/local/sbin/lisa-wifi-setup")
    return identity.group(1), password.group(1)


def main() -> None:
    identity, password = shipped_credentials()
    print(f"testing with shipped identity: {identity}", flush=True)

    print("== reset any previous attempt ==", flush=True)
    sh("pkill hostapd || true")
    sh("systemctl stop 'netplan-wpa-*.service' || true")
    sh("rm -f /etc/netplan/70-lisa-wifi.yaml")
    sh("rmmod mac80211_hwsim 2>/dev/null || true")

    print("== harness tools ==", flush=True)
    # DPkg::Lock::Timeout: the join service may be apt-installing tailscale
    # concurrently on first boot (it retries with the dummy key) — wait for it.
    sh("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq"
       " -o DPkg::Lock::Timeout=300 hostapd iw > /dev/null", check=True)
    sh("systemctl stop hostapd; systemctl disable hostapd 2>/dev/null || true")

    print("== load virtual radios ==", flush=True)
    sh("modprobe mac80211_hwsim radios=2", check=True)
    time.sleep(2)

    print("== rename AP radio to zap0 (sorts after wl*; detector ignores it) ==", flush=True)
    radios = wifi_interfaces()
    if len(radios) < 2:
        sys.exit(f"expected 2 hwsim radios, found {radios}")
    ap_src = radios[0]
    sh(f"ip link set {ap_src} down && ip link set {ap_src} name zap0", check=True)

    print("== EAP server cert ==", flush=True)
    cfg = pathlib.Path("/etc/lisa-test")
    cfg.mkdir(exist_ok=True)
    sh("openssl req -x509 -newkey rsa:2048 -nodes -days 2"
       " -keyout /etc/lisa-test/server.key -out /etc/lisa-test/server.crt"
       " -subj /CN=radius.test.local 2>/dev/null", check=True)

    print("== hostapd: WPA2-Enterprise AP with builtin EAP server ==", flush=True)
    (cfg / "eap_users").write_text(
        f'* PEAP\n"{identity}" MSCHAPV2 "{password}" [2]\n'
    )
    (cfg / "hostapd.conf").write_text(
        "interface=zap0\ndriver=nl80211\nssid=eduroam\nhw_mode=g\nchannel=1\n"
        "auth_algs=1\nwpa=2\nwpa_key_mgmt=WPA-EAP\nrsn_pairwise=CCMP\n"
        "ieee8021x=1\neap_server=1\n"
        "eap_user_file=/etc/lisa-test/eap_users\n"
        "ca_cert=/etc/lisa-test/server.crt\n"
        "server_cert=/etc/lisa-test/server.crt\n"
        "private_key=/etc/lisa-test/server.key\n"
    )
    sh("hostapd -B /etc/lisa-test/hostapd.conf", check=True)

    print("== DHCP server on the AP side (networkd) ==", flush=True)
    rundir = pathlib.Path("/run/systemd/network")
    rundir.mkdir(parents=True, exist_ok=True)
    (rundir / "50-zap0.network").write_text(
        "[Match]\nName=zap0\n[Network]\nAddress=10.99.0.1/24\nDHCPServer=yes\n"
    )
    sh("systemctl restart systemd-networkd", check=True)
    time.sleep(3)

    print("== run the SHIPPED wifi setup script ==", flush=True)
    sh("/usr/local/sbin/lisa-wifi-setup", check=True)

    print("== wait for association + DHCP ==", flush=True)
    client = next((i for i in wifi_interfaces() if i.startswith("wl")), None)
    if not client:
        sys.exit("no client wl* radio found")
    got_ip = False
    for _ in range(30):
        if "inet 10.99.0." in sh(f"ip -4 addr show {client}"):
            got_ip = True
            break
        time.sleep(2)

    print("===== RESULTS =====", flush=True)
    print(sh(f"iw dev {client} link"), flush=True)
    print(sh(f"ip -4 addr show {client} | grep inet || true"), flush=True)
    wpa_state = sh(f"wpa_cli -i {client} status 2>/dev/null | awk -F= '$1==\"wpa_state\"{{print $2}}'")
    print(sh("journalctl --no-pager -n 300 | grep -iE 'CTRL-EVENT-EAP-SUCCESS|CTRL-EVENT-CONNECTED' | tail -3"), flush=True)

    if got_ip and wpa_state == "COMPLETED":
        print("HWSIM-EDUROAM: PASS", flush=True)
    else:
        print(f"HWSIM-EDUROAM: FAIL (got_ip={got_ip} wpa_state={wpa_state})", flush=True)
        print(sh("journalctl --no-pager -n 100 | grep -iE 'wpa_supplicant|hostapd' | tail -20"), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
