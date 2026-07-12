#!/usr/bin/env python3
"""Fetch build inputs: pristine Ubuntu ISO (cache-aware, checksum-verified),
de0ch's public SSH keys, and the offline deb bundle from a 26.04 container.
"""
import hashlib
import pathlib
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from util import log, run

RELEASE_URL = "https://releases.ubuntu.com/26.04"


def download(url: str, dest: pathlib.Path) -> None:
    log(f"downloading {url} -> {dest}")
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def main() -> None:
    iso_dir = pathlib.Path("iso")
    iso_dir.mkdir(exist_ok=True)
    pathlib.Path("debs").mkdir(exist_ok=True)

    log("== resolve + download ISO ==")
    download(f"{RELEASE_URL}/SHA256SUMS", iso_dir / "SHA256SUMS")
    sums = (iso_dir / "SHA256SUMS").read_text()
    m = re.search(r"^([0-9a-f]{64}) \*?(.*live-server-amd64\.iso)$", sums, re.M)
    if not m:
        sys.exit("live-server ISO not found in SHA256SUMS")
    expected_sha, iso_name = m.group(1), m.group(2)
    (iso_dir / "iso-name.txt").write_text(iso_name + "\n")

    iso_path = iso_dir / iso_name
    if not iso_path.exists():
        download(f"{RELEASE_URL}/{iso_name}", iso_path)

    log("== verify checksum ==")
    h = hashlib.sha256()
    with open(iso_path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    if h.hexdigest() != expected_sha:
        iso_path.unlink()
        sys.exit(f"checksum mismatch for {iso_name} (file deleted; re-run)")
    log(f"checksum OK: {iso_name}")

    log("== fetch authorized keys ==")
    with urllib.request.urlopen("https://github.com/de0ch.keys", timeout=30) as r:
        keys = r.read().decode()
    if not keys.strip():
        sys.exit("de0ch.keys is empty")
    pathlib.Path("de0ch.keys").write_text(keys)
    log(keys.strip())

    log("== download deb bundle (wpasupplicant/curl closure, 26.04 container) ==")
    run([
        "docker", "run", "--rm", "-v", f"{pathlib.Path.cwd()}/debs:/out",
        "ubuntu:26.04", "bash", "-ec",
        "apt-get update -qq && "
        "apt-get install --download-only --no-install-recommends -y "
        "-o Dir::Cache::archives=/out wpasupplicant curl > /dev/null && "
        "rm -rf /out/partial /out/lock && chmod -R a+r /out",
    ])
    for deb in sorted(pathlib.Path("debs").glob("*.deb")):
        log(f"  {deb.name} ({deb.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
