#!/usr/bin/env python3
"""Host-side wrapper: run verify_system.py as root inside the guest.

Decides expect-ts from whether TS_AUTHKEY_TEST is a real key (the injected
join should then succeed) and streams the guest script over SSH stdin.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from util import log, ssh_sudo

def main() -> None:
    expect_ts = 1 if os.environ.get("TS_AUTHKEY_TEST", "").startswith("tskey-auth-") else 0
    log(f"expect-ts={expect_ts}")
    script = (pathlib.Path(__file__).parent / "verify_system.py").read_text()
    r = ssh_sudo(script, args=(2, expect_ts), timeout=600)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
