#!/bin/bash
# Remaster the Ubuntu live-server ISO with an embedded autoinstall seed.
# Usage: build-iso.sh <variant> <seed-dir> <out-iso>
# Expects the pristine ISO in iso/ (downloaded by fetch-inputs.sh).
set -euo pipefail

VARIANT="${1:?variant}"
SEED_DIR="${2:?seed dir}"
OUT_ISO="${3:?output iso path}"
ISO_DIR="${ISO_DIR:-iso}"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

ISO_NAME=$(cat "$ISO_DIR/iso-name.txt")

echo "== add debs to seed =="
if compgen -G "debs/*.deb" > /dev/null; then
  mkdir -p "$SEED_DIR/debs"
  cp debs/*.deb "$SEED_DIR/debs/"
  ls "$SEED_DIR/debs"
fi

echo "== patch grub.cfg =="
xorriso -osirrox on -indev "$ISO_DIR/$ISO_NAME" -extract /boot/grub/grub.cfg "$STAGE/grub.cfg" 2>/dev/null
chmod +w "$STAGE/grub.cfg"
sed -i 's|set timeout=.*|set timeout=3|' "$STAGE/grub.cfg"
sed -i 's|\(linux\s\+/casper/[^ ]*vmlinuz[^-]*\)---|\1autoinstall ds=nocloud\\;s=/cdrom/nocloud/  ---|' "$STAGE/grub.cfg"
grep -q 'autoinstall' "$STAGE/grub.cfg" || { echo "grub patch failed"; exit 1; }

echo "== repack =="
rm -f "$OUT_ISO"
xorriso -indev "$ISO_DIR/$ISO_NAME" -outdev "$OUT_ISO" \
  -boot_image any replay \
  -map "$SEED_DIR" /nocloud \
  -map "$STAGE/grub.cfg" /boot/grub/grub.cfg

ls -l "$OUT_ISO"
sha256sum "$OUT_ISO" | tee "$OUT_ISO.sha256"
echo "BUILD OK: $OUT_ISO ($VARIANT)"
