#!/usr/bin/env python3
"""Inject the CI tailscale key into the booted test VM.

The test ISO is always built with a dummy key so no artifact ever contains a
real credential; the real key exists only in CI and enters the guest over SSH
at test time. The join service re-reads /etc/lisa-tskey on each attempt, so a
restart makes it pick up the injected key immediately.
"""
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from util import GUEST, SSH_OPTS, env_required, log

def main() -> None:
    key = os.environ.get("TS_AUTHKEY_TEST", "")
    if not key.startswith("tskey-auth-"):
        log("dummy/absent CI tailscale key - skipping injection (join stays retry-pending)")
        return
    password = env_required("CONSOLE_PASSWORD")
    remote = ("sudo -S -p '' bash -c "
              "'umask 077; cat > /etc/lisa-tskey"
              " && systemctl restart --no-block lisa-tailscale-join.service"
              " && echo key-injected'")
    r = subprocess.run(
        ["ssh", *SSH_OPTS, GUEST, remote],
        input=f"{password}\n{key}".encode(), timeout=30,
    )
    if r.returncode != 0:
        sys.exit(f"injection failed rc={r.returncode}")


if __name__ == "__main__":
    main()
