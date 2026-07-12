#!/bin/bash
# QEMU/KVM orchestration for install testing on GitHub Actions runners.
#
#   vm.sh install <iso>   boot the installer ISO against a fresh disk; the
#                         autoinstall powers the VM off when done (qemu exits)
#   vm.sh boot            boot the installed disk in the background with
#                         ssh forwarded to 127.0.0.1:2222; waits for sshd
#   vm.sh stop            kill the background VM
set -euo pipefail

DISK=${DISK:-lisa.qcow2}
MEM=${MEM:-4096}
SERIAL=${SERIAL:-serial-$1.log}
OVMF_CODE=/usr/share/OVMF/OVMF_CODE_4M.fd
OVMF_VARS_SRC=/usr/share/OVMF/OVMF_VARS_4M.fd
SSH_PORT=${SSH_PORT:-2222}

common_args() {
  echo "-enable-kvm -machine q35 -cpu host -m $MEM -smp $(nproc) \
    -drive if=pflash,format=raw,readonly=on,file=$OVMF_CODE \
    -drive if=pflash,format=raw,file=ovmf_vars.fd \
    -drive file=$DISK,if=virtio,format=qcow2 \
    -display none -serial file:$SERIAL"
}

case "$1" in
  install)
    ISO="${2:?iso path}"
    qemu-img create -f qcow2 "$DISK" 20G
    cp "$OVMF_VARS_SRC" ovmf_vars.fd
    echo "== unattended install from $ISO (this takes 10-25 min) =="
    # shellcheck disable=SC2046
    timeout 2400 qemu-system-x86_64 $(common_args) \
      -cdrom "$ISO" \
      -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
      || { rc=$?; echo "qemu exited rc=$rc"; tail -50 "$SERIAL"; exit $rc; }
    echo "== installer powered off =="
    ;;
  boot)
    echo "== booting installed system =="
    # shellcheck disable=SC2046
    nohup qemu-system-x86_64 $(common_args) \
      -netdev user,id=n0,hostfwd=tcp:127.0.0.1:${SSH_PORT}-:22 \
      -device virtio-net-pci,netdev=n0 \
      > qemu-boot.out 2>&1 &
    echo $! > qemu.pid
    echo "== waiting for sshd on :$SSH_PORT =="
    for i in $(seq 1 90); do
      if ssh-keyscan -T 3 -p "$SSH_PORT" 127.0.0.1 2>/dev/null | grep -q ssh-ed25519; then
        echo "sshd is up (after ~$((i*5))s)"
        exit 0
      fi
      kill -0 "$(cat qemu.pid)" 2>/dev/null || { echo "qemu died"; tail -50 "$SERIAL"; exit 1; }
      sleep 5
    done
    echo "sshd never came up"; tail -80 "$SERIAL"; exit 1
    ;;
  stop)
    [ -f qemu.pid ] && kill "$(cat qemu.pid)" 2>/dev/null || true
    sleep 2
    ;;
  *)
    echo "usage: vm.sh install <iso> | boot | stop"; exit 2
    ;;
esac
