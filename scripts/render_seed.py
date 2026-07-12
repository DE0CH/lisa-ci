#!/usr/bin/env python3
"""Render seed templates into a concrete NoCloud seed directory.

Literal string replacement (no shell/envsubst) so values containing $, /, &
etc. (crypt hashes, passwords) cannot be mangled.

Usage: render_seed.py --variant test|final --out <dir>
Env:   TS_AUTHKEY always; EDUROAM_USERNAME, EDUROAM_PASSWORD for --variant
       final only (the test variant generates dummy credentials in code).
Files: de0ch.keys (fetched by CI), test_key.pub (test variant only)

The account password is generated randomly here and discarded: the installed
system is SSH-key-only with passwordless sudo (cloud-image convention).
"""
import argparse
import os
import pathlib
import secrets as pysecrets
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        sys.exit(f"missing required env var: {name}")
    return v

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["test", "final"], required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    (out / "payload").mkdir(parents=True, exist_ok=True)

    keys = [
        line.strip()
        for line in (ROOT / "de0ch.keys").read_text().splitlines()
        if line.strip()
    ]
    if args.variant == "test":
        keys.append((ROOT / "test_key.pub").read_text().strip())
    keys_yaml = "\n".join(f'      - "{k}"' for k in keys)

    # Random, discarded: nobody knows this password; access is SSH + NOPASSWD
    # sudo (see the sudoers late-command in the template).
    throwaway = pysecrets.token_urlsafe(24)
    password_hash = subprocess.run(
        ["openssl", "passwd", "-6", throwaway],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    user_data = (ROOT / "seed" / "user-data.tmpl").read_text()
    user_data = user_data.replace("@PASSWORD_HASH@", password_hash)
    user_data = user_data.replace("@TS_AUTHKEY@", env("TS_AUTHKEY"))
    user_data = user_data.replace("@AUTHORIZED_KEYS@", keys_yaml)
    for tok in ("@PASSWORD_HASH@", "@TS_AUTHKEY@", "@AUTHORIZED_KEYS@"):
        assert tok not in user_data, f"unreplaced token {tok}"
    (out / "user-data").write_text(user_data, newline="\n")

    shutil.copy(ROOT / "seed" / "meta-data", out / "meta-data")

    # The test variant never touches the eduroam secrets: it gets throwaway
    # credentials generated right here. The hwsim test reads them back out of
    # the shipped script on the guest, so the fake AP always matches. Only the
    # release (final) render consumes the EDUROAM_* secrets.
    if args.variant == "test":
        eduroam_user = f"dummy-{pysecrets.token_hex(4)}@example.edu"
        eduroam_pass = f"dummy-{pysecrets.token_hex(8)}"
    else:
        eduroam_user = env("EDUROAM_USERNAME")
        eduroam_pass = env("EDUROAM_PASSWORD")

    wifi = (ROOT / "payload" / "lisa-wifi-setup.tmpl").read_text()
    wifi = wifi.replace("@EDUROAM_USERNAME@", eduroam_user)
    wifi = wifi.replace("@EDUROAM_PASSWORD@", eduroam_pass)
    assert "@EDUROAM" not in wifi
    (out / "payload" / "lisa-wifi-setup").write_text(wifi, newline="\n")
    shutil.copy(
        ROOT / "payload" / "lisa-wifi-setup.service",
        out / "payload" / "lisa-wifi-setup.service",
    )

    import yaml  # PyYAML is preinstalled on GitHub runners
    yaml.safe_load((out / "user-data").read_text())
    print(f"seed rendered: {out} (variant={args.variant}, {len(keys)} ssh keys)")

if __name__ == "__main__":
    main()
