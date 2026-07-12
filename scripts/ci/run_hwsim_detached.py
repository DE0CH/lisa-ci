#!/usr/bin/env python3
"""Run the in-guest eduroam test detached via systemd-run and poll for the
verdict. Detached because the test triggers `netplan apply`, which can drop
the very SSH session that launched it.
"""
import pathlib
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from util import GUEST, SSH_OPTS, env_required, log, ssh_sudo_shell

def main() -> None:
    identity = env_required("EDUROAM_IDENTITY")
    password = env_required("EDUROAM_PASSWORD")
    console_pw = env_required("CONSOLE_PASSWORD")

    log("== upload test script ==")
    script = (pathlib.Path(__file__).parent / "hwsim_eduroam_test.py").read_text()
    r = subprocess.run(
        ["ssh", *SSH_OPTS, GUEST, "cat > /tmp/hwsim-test.py"],
        input=script.encode(), timeout=30,
    )
    if r.returncode != 0:
        sys.exit("upload failed")

    log("== launch detached ==")
    unit_cmd = (
        "sudo -S -p '' systemd-run --no-block --unit=lisa-hwsim-test "
        f"--setenv=EDUROAM_IDENTITY={shlex.quote(identity)} "
        f"--setenv=EDUROAM_PASSWORD={shlex.quote(password)} "
        "python3 /tmp/hwsim-test.py"
    )
    r = subprocess.run(["ssh", *SSH_OPTS, GUEST, unit_cmd],
                       input=f"{console_pw}\n".encode(), timeout=30)
    if r.returncode != 0:
        sys.exit("systemd-run launch failed")

    log("== poll for verdict ==")
    verdict = ""
    for _ in range(60):
        r = ssh_sudo_shell(
            "journalctl -u lisa-hwsim-test --no-pager 2>/dev/null"
            " | grep -oE 'HWSIM-EDUROAM: (PASS|FAIL).*' | tail -1",
            timeout=25,
        )
        verdict = r.stdout.decode(errors="replace").strip()
        if verdict:
            break
        time.sleep(5)

    log("== full test log ==")
    r = ssh_sudo_shell("journalctl -u lisa-hwsim-test --no-pager | tail -80",
                       timeout=40)
    print(r.stdout.decode(errors="replace"), flush=True)

    log(f"verdict: {verdict or 'NONE (timed out)'}")
    sys.exit(0 if "PASS" in verdict else 1)


if __name__ == "__main__":
    main()
