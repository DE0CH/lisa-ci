#!/usr/bin/env python3
"""Publish the verified release ISO as a GitHub Release.

Usage: make_release.py <run-number> <sha>
Env:   GH_TOKEN (the workflow's github.token)

GitHub caps release assets at 2 GiB, so the ISO ships as a multipart 7z
archive (store mode: the ISO is mostly compressed squashfs already; the 7z
container adds native splitting + CRC integrity).
"""
import pathlib
import subprocess
import sys

NOTES = """Fully CI-tested unattended Ubuntu Server 26.04 installer for lisa.

The ISO ships as a multipart 7z (GitHub caps release assets at 2 GiB).
Extract with 7-Zip (open the .001 file), or:

    7z x lisa-final.7z.001
    sha256sum -c lisa-final.iso.sha256

Then write to USB with any raw imaging tool (dd / Rufus dd mode / balenaEtcher).
Built from commit {sha}.
"""


def main() -> None:
    run_number, sha = sys.argv[1], sys.argv[2]

    subprocess.run(
        ["7z", "a", "-v1900m", "-mx=0", "lisa-final.7z", "lisa-final.iso"],
        check=True,
    )
    parts = sorted(str(p) for p in pathlib.Path(".").glob("lisa-final.7z.*"))
    print(f"multipart 7z: {parts}", flush=True)

    tag = f"build-{run_number}"
    subprocess.run(
        ["gh", "release", "create", tag, *parts, "lisa-final.iso.sha256",
         "--title", f"lisa installer (build {run_number}, {sha[:9]})",
         "--latest", "--notes", NOTES.format(sha=sha)],
        check=True,
    )
    print(f"released {tag}", flush=True)


if __name__ == "__main__":
    main()
