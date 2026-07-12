#!/usr/bin/env python3
"""Publish the verified release ISO as a GitHub Release.

Usage: make_release.py <run-number> <sha>
Env:   GH_TOKEN (the workflow's github.token)

GitHub caps release assets at 2 GiB, so the ISO is split into parts; the
release notes carry the reassembly instructions.
"""
import pathlib
import subprocess
import sys

PART_SIZE = 1900 * 1024 * 1024  # under the 2 GiB asset cap

NOTES = """Fully CI-tested unattended Ubuntu Server 26.04 installer for lisa.

Assets are split because GitHub caps release assets at 2 GiB. Reassemble:

    # Linux / macOS / Git Bash
    cat lisa-final.iso.part-* > lisa-final.iso
    sha256sum -c lisa-final.iso.sha256

    # Windows cmd
    copy /b lisa-final.iso.part-00+lisa-final.iso.part-01 lisa-final.iso

Then write to USB with any raw imaging tool (dd / Rufus dd mode / balenaEtcher).
Built from commit {sha}.
"""


def main() -> None:
    run_number, sha = sys.argv[1], sys.argv[2]
    iso = pathlib.Path("lisa-final.iso")

    parts = []
    with open(iso, "rb") as src:
        idx = 0
        while chunk := src.read(PART_SIZE):
            part = pathlib.Path(f"lisa-final.iso.part-{idx:02d}")
            part.write_bytes(chunk)
            parts.append(str(part))
            idx += 1
    print(f"split into {len(parts)} parts", flush=True)

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
