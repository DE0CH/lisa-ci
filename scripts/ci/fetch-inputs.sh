#!/bin/bash
# Download the pristine Ubuntu ISO (if not restored from cache), verify its
# checksum, fetch de0ch's public SSH keys, and download the deb bundle for
# offline Wi-Fi capability using an Ubuntu 26.04 container (runner is 24.04).
set -euo pipefail

RELEASE_URL="https://releases.ubuntu.com/26.04"
mkdir -p iso debs

echo "== resolve + download ISO =="
curl -fsSL "$RELEASE_URL/SHA256SUMS" -o iso/SHA256SUMS
ISO_NAME=$(awk '/live-server-amd64.iso/ {gsub(/\*/,"",$2); print $2; exit}' iso/SHA256SUMS)
echo "$ISO_NAME" > iso/iso-name.txt
if [ ! -f "iso/$ISO_NAME" ]; then
  curl -fL --retry 3 -o "iso/$ISO_NAME" "$RELEASE_URL/$ISO_NAME"
fi
(cd iso && grep "$ISO_NAME" SHA256SUMS | sha256sum -c -)

echo "== fetch authorized keys =="
curl -fsSL https://github.com/de0ch.keys -o de0ch.keys
[ -s de0ch.keys ] || { echo "de0ch.keys empty"; exit 1; }
cat de0ch.keys

echo "== download deb bundle (wpasupplicant/curl closure from a 26.04 container) =="
docker run --rm -v "$PWD/debs:/out" ubuntu:26.04 bash -ec '
  apt-get update -qq
  apt-get install --download-only --no-install-recommends -y \
    -o Dir::Cache::archives=/out wpasupplicant curl > /dev/null
  rm -rf /out/partial /out/lock
  chmod -R a+r /out
'
ls -s debs/
