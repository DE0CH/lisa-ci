#!/usr/bin/env python3
"""Render seed templates into a concrete NoCloud seed directory.

Literal string replacement (no shell/envsubst) so values containing $, /, &
etc. (crypt hashes, passwords) cannot be mangled.

Usage: render-seed.py --variant test|final --out <dir>
Env:   PASSWORD_HASH, TS_AUTHKEY, EDUROAM_IDENTITY, EDUROAM_PASSWORD
Files: de0ch.keys (fetched by CI), test_key.pub (test variant only)
"""
import argparse
import os
import pathlib
import shutil
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

    user_data = (ROOT / "seed" / "user-data.tmpl").read_text()
    user_data = user_data.replace("@PASSWORD_HASH@", env("PASSWORD_HASH"))
    user_data = user_data.replace("@TS_AUTHKEY@", env("TS_AUTHKEY"))
    user_data = user_data.replace("@AUTHORIZED_KEYS@", keys_yaml)
    for tok in ("@PASSWORD_HASH@", "@TS_AUTHKEY@", "@AUTHORIZED_KEYS@"):
        assert tok not in user_data, f"unreplaced token {tok}"
    (out / "user-data").write_text(user_data, newline="\n")

    shutil.copy(ROOT / "seed" / "meta-data", out / "meta-data")

    wifi = (ROOT / "payload" / "lisa-wifi-setup.tmpl").read_text()
    wifi = wifi.replace("@EDUROAM_IDENTITY@", env("EDUROAM_IDENTITY"))
    wifi = wifi.replace("@EDUROAM_PASSWORD@", env("EDUROAM_PASSWORD"))
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
