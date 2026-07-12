#!/usr/bin/env python3
"""Remaster the Ubuntu live-server ISO with an embedded autoinstall seed.

Usage: build_iso.py <variant> <seed-dir> <out-iso>
Expects the pristine ISO under iso/ (see scripts/ci/fetch_inputs.py) and the
offline deb bundle under debs/.
"""
import hashlib
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent / "ci"))
from util import log, run


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit("usage: build_iso.py <variant> <seed-dir> <out-iso>")
    variant, seed_dir, out_iso = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3]
    iso_dir = pathlib.Path("iso")
    iso_path = iso_dir / (iso_dir / "iso-name.txt").read_text().strip()

    log("== add debs to seed ==")
    debs = sorted(pathlib.Path("debs").glob("*.deb"))
    if debs:
        (seed_dir / "debs").mkdir(exist_ok=True)
        for deb in debs:
            shutil.copy(deb, seed_dir / "debs" / deb.name)
        log(f"bundled {len(debs)} debs")

    with tempfile.TemporaryDirectory() as stage:
        grub_cfg = pathlib.Path(stage) / "grub.cfg"

        log("== patch grub.cfg ==")
        run(["xorriso", "-osirrox", "on", "-indev", iso_path,
             "-extract", "/boot/grub/grub.cfg", grub_cfg])
        grub_cfg.chmod(0o644)
        cfg = grub_cfg.read_text()
        cfg = re.sub(r"set timeout=.*", "set timeout=3", cfg)
        cfg, n = re.subn(
            r"(linux\s+/casper/\S*vmlinuz[^-]*)---",
            r"\1autoinstall ds=nocloud\\;s=/cdrom/nocloud/  ---",
            cfg,
        )
        if n == 0 or "autoinstall" not in cfg:
            sys.exit("grub patch failed")
        grub_cfg.write_text(cfg, newline="\n")
        log(f"patched {n} kernel line(s)")

        log("== repack ==")
        pathlib.Path(out_iso).unlink(missing_ok=True)
        run(["xorriso", "-indev", iso_path, "-outdev", out_iso,
             "-boot_image", "any", "replay",
             "-map", seed_dir, "/nocloud",
             "-map", grub_cfg, "/boot/grub/grub.cfg"])

    h = hashlib.sha256()
    with open(out_iso, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    digest = h.hexdigest()
    pathlib.Path(out_iso + ".sha256").write_text(f"{digest}  {out_iso}\n")
    size_mb = pathlib.Path(out_iso).stat().st_size // (1 << 20)
    log(f"BUILD OK: {out_iso} ({variant}, {size_mb} MiB, sha256 {digest})")


if __name__ == "__main__":
    main()
