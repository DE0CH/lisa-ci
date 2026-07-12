#!/usr/bin/env python3
"""In-guest verification. Runs as root inside the installed VM (delivered over
SSH as `sudo python3 - <n-keys> <expect-ts>`). Stdlib only, no repo imports.
"""
import pathlib
import subprocess
import sys
import time

failures = []


def sh(cmd: str) -> str:
    r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True)
    return r.stdout.strip()


def chk(name: str, expected: str, actual: str) -> None:
    if expected == actual:
        print(f"PASS: {name} = {expected}", flush=True)
    else:
        print(f"FAIL: {name} expected [{expected}] got [{actual}]", flush=True)
        failures.append(name)


def main() -> None:
    expect_keys = sys.argv[1] if len(sys.argv) > 1 else "2"
    expect_ts = sys.argv[2] if len(sys.argv) > 2 else "1"

    # Settle first: timezone/runcmd are cloud-init stages that finish after
    # sshd is already accepting connections.
    print("-- waiting for cloud-init to finish (up to 300s) --", flush=True)
    subprocess.run(["timeout", "300", "cloud-init", "status", "--wait"])

    chk("hostname", "lisa", sh("hostname"))
    chk("timezone", "Asia/Hong_Kong", sh("timedatectl show -p Timezone --value"))

    auth_keys = pathlib.Path("/home/deyao/.ssh/authorized_keys").read_text()
    key_lines = [l for l in auth_keys.splitlines() if l.strip().startswith("ssh-")]
    chk("authorized_keys_count", expect_keys, str(len(key_lines)))
    chk("de0ch_key_present", "1", str(sum("GJ9quHj1tvkeftOu" in l for l in key_lines)))

    sshd = sh("sshd -T")
    conf = dict(l.split(None, 1) for l in sshd.splitlines() if " " in l)
    chk("sshd_password_auth", "no", conf.get("passwordauthentication", "?"))
    chk("sshd_kbdint_auth", "no", conf.get("kbdinteractiveauthentication", "?"))

    sudoers = pathlib.Path("/etc/sudoers.d/90-deyao")
    chk("nopasswd_sudo", "deyao ALL=(ALL) NOPASSWD:ALL",
        sudoers.read_text().strip() if sudoers.exists() else "missing")

    for pkg in ("wpasupplicant", "curl"):
        status = sh(f"dpkg-query -W -f='${{db:Status-Status}}' {pkg} 2>/dev/null")
        chk(f"{pkg}_installed", "installed", status)
    apt_hist = pathlib.Path("/var/log/apt/history.log").read_text()
    chk("debs_installed_offline", "1",
        "1" if "Dir::Etc::sourcelist=/dev/null" in apt_hist and "lisa-debs" in apt_hist else "0")

    chk("wifi_setup_enabled", "enabled", sh("systemctl is-enabled lisa-wifi-setup.service"))
    chk("wifi_setup_script_mode", "755",
        oct(pathlib.Path("/usr/local/sbin/lisa-wifi-setup").stat().st_mode & 0o777)[2:])
    wifi_script = pathlib.Path("/usr/local/sbin/lisa-wifi-setup").read_text()
    chk("wifi_creds_in_script", "1", "1" if "method: peap" in wifi_script else "0")

    key_file = pathlib.Path("/etc/lisa-tskey")
    if expect_ts == "1":
        print("-- waiting up to 120s for tailscale join --", flush=True)
        ts_ip = ""
        for _ in range(24):
            ts_ip = sh("tailscale ip -4 2>/dev/null | head -1")
            if ts_ip:
                break
            time.sleep(5)
        if ts_ip.startswith("100."):
            print(f"PASS: tailscale joined ({ts_ip})", flush=True)
        else:
            print(f"FAIL: tailscale did not join (ip=[{ts_ip}])", flush=True)
            print(sh("journalctl -u lisa-tailscale-join --no-pager | tail -20"), flush=True)
            failures.append("tailscale_join")
        # The join script removes the key and disables itself moments after
        # `tailscale up` returns — poll for the settled end state.
        print("-- waiting up to 60s for join cleanup --", flush=True)
        for _ in range(12):
            if not key_file.exists() and \
               sh("systemctl is-enabled lisa-tailscale-join.service") == "disabled":
                break
            time.sleep(5)
        chk("tailscale_key_removed", "missing",
            "present" if key_file.exists() else "missing")
        chk("join_service_disabled", "disabled",
            sh("systemctl is-enabled lisa-tailscale-join.service"))
    else:
        # Dummy key: the join must keep retrying across boots — key stays,
        # unit stays enabled. Correct behavior for a machine that can't reach
        # its tailnet yet; asserted by dummy-credential (public repo) builds.
        print("-- dummy tailscale key: asserting retry-pending state --", flush=True)
        chk("tailscale_key_kept", "present",
            "present" if key_file.exists() else "missing")
        chk("join_service_still_enabled", "enabled",
            sh("systemctl is-enabled lisa-tailscale-join.service"))

    if failures:
        print(f"VERIFY-SYSTEM: FAILURES: {', '.join(failures)}", flush=True)
        sys.exit(1)
    print("VERIFY-SYSTEM: ALL PASS", flush=True)


if __name__ == "__main__":
    main()
