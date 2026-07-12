#!/usr/bin/env python3
"""QEMU/KVM orchestration for install testing on GitHub Actions runners.

  vm.py install <iso>   boot the installer ISO against a fresh disk; the
                        autoinstall powers the VM off when done (qemu exits)
  vm.py boot [--restrict]
                        boot the installed disk in the background with ssh
                        forwarded to 127.0.0.1:2222; waits for sshd.
                        --restrict blocks all guest-initiated traffic (QEMU
                        slirp restrict=on): sshd stays reachable but the guest
                        cannot reach the internet — used when booting the
                        release image so its baked tailscale key cannot fire.
  vm.py stop            kill the background VM
"""
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from util import log, run

DISK = os.environ.get("DISK", "lisa.qcow2")
MEM = os.environ.get("MEM", "4096")
SSH_PORT = os.environ.get("SSH_PORT", "2222")
OVMF_CODE = "/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS = "/usr/share/OVMF/OVMF_VARS_4M.fd"


def common_args(serial_log: str) -> list:
    return [
        "-enable-kvm", "-machine", "q35", "-cpu", "host",
        "-m", MEM, "-smp", str(os.cpu_count() or 2),
        "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
        "-drive", "if=pflash,format=raw,file=ovmf_vars.fd",
        "-drive", f"file={DISK},if=virtio,format=qcow2",
        "-display", "none", "-serial", f"file:{serial_log}",
    ]


def tail(path: str, lines: int = 60) -> None:
    try:
        content = pathlib.Path(path).read_text(errors="replace").splitlines()
        print("\n".join(content[-lines:]), flush=True)
    except OSError as e:
        log(f"(no serial log: {e})")


def cmd_install(iso: str) -> None:
    run(["qemu-img", "create", "-f", "qcow2", DISK, "20G"])
    shutil.copy(OVMF_VARS, "ovmf_vars.fd")
    log(f"== unattended install from {iso} (10-25 min) ==")
    cmd = ["qemu-system-x86_64", *common_args("serial-install.log"),
           "-cdrom", iso,
           "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0"]
    try:
        run(cmd, timeout=2400)
    except subprocess.TimeoutExpired:
        log("INSTALL TIMED OUT after 2400s; serial tail:")
        tail("serial-install.log")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        log(f"qemu exited rc={e.returncode}; serial tail:")
        tail("serial-install.log")
        sys.exit(e.returncode)
    log("== installer powered off ==")


def cmd_boot(restrict: bool = False) -> None:
    log(f"== booting installed system (restrict={restrict}) ==")
    netdev = f"user,id=n0,hostfwd=tcp:127.0.0.1:{SSH_PORT}-:22"
    if restrict:
        netdev += ",restrict=on"
    cmd = ["qemu-system-x86_64", *common_args("serial-boot.log"),
           "-netdev", netdev,
           "-device", "virtio-net-pci,netdev=n0"]
    log(f"+ {' '.join(cmd)} &")
    with open("qemu-boot.out", "wb") as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
    pathlib.Path("qemu.pid").write_text(str(proc.pid))

    log(f"== waiting for sshd on :{SSH_PORT} ==")
    for i in range(90):
        scan = subprocess.run(
            ["ssh-keyscan", "-T", "3", "-p", SSH_PORT, "127.0.0.1"],
            capture_output=True, timeout=15,
        )
        if b"ssh-ed25519" in scan.stdout:
            log(f"sshd is up (after ~{i * 5}s)")
            return
        if proc.poll() is not None:
            log("qemu died; serial tail:")
            tail("serial-boot.log")
            sys.exit(1)
        time.sleep(5)
    log("sshd never came up; serial tail:")
    tail("serial-boot.log", 80)
    sys.exit(1)


def cmd_stop() -> None:
    try:
        pid = int(pathlib.Path("qemu.pid").read_text())
        os.kill(pid, signal.SIGTERM)
        log(f"sent SIGTERM to qemu pid {pid}")
        time.sleep(2)
    except (OSError, ValueError) as e:
        log(f"stop: nothing to do ({e})")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: vm.py install <iso> | boot | stop")
    match sys.argv[1]:
        case "install":
            cmd_install(sys.argv[2])
        case "boot":
            cmd_boot(restrict="--restrict" in sys.argv[2:])
        case "stop":
            cmd_stop()
        case _:
            sys.exit("usage: vm.py install <iso> | boot | stop")


if __name__ == "__main__":
    main()
