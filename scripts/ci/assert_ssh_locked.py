#!/usr/bin/env python3
"""Negative SSH checks against the final image: the CI test key must be
rejected and password auth must not even be offered — proving the image
trusts only the de0ch.keys identity.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from util import GUEST, SSH_OPTS, log

def attempt(name: str, extra_opts: list) -> None:
    r = subprocess.run(
        ["ssh", *SSH_OPTS, *extra_opts, GUEST, "echo BREACH"],
        capture_output=True, text=True, timeout=30,
    )
    out = (r.stdout + r.stderr).strip()
    log(out)
    if r.returncode == 0:
        sys.exit(f"FAIL: {name} was accepted by the final image")
    if "Permission denied (publickey)" not in out:
        sys.exit(f"FAIL: {name}: unexpected error (expected publickey-only denial)")
    log(f"PASS: {name} rejected, publickey-only")


def main() -> None:
    attempt("test key", [])
    attempt("password auth", ["-o", "PreferredAuthentications=password",
                              "-o", "PubkeyAuthentication=no"])


if __name__ == "__main__":
    main()
