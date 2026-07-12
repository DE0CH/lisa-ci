"""Shared helpers for the CI scripts (stdlib only)."""
import os
import subprocess
import sys

SSH_OPTS = [
    "-i", "test_key", "-p", "2222",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "UserKnownHostsFile=known_hosts_vm",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "ServerAliveInterval=5",
    "-o", "ServerAliveCountMax=3",
]
GUEST = "deyao@127.0.0.1"


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd, **kw):
    """subprocess.run with echo; check=True unless overridden."""
    kw.setdefault("check", True)
    log(f"+ {' '.join(map(str, cmd))}")
    return subprocess.run([str(c) for c in cmd], **kw)


def env_required(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        sys.exit(f"missing required env var: {name}")
    return v


def ssh_sudo(script: str, args=(), timeout=120, extra_stdin: str = ""):
    """Run `script` as root inside the guest via `sudo python3 -`.

    stdin layout: first line is the console password (consumed by sudo -S),
    the rest is the script text (consumed by python3 -), then EOF.
    Returns the CompletedProcess (check is left to callers).
    """
    password = env_required("CONSOLE_PASSWORD")
    remote = "sudo -S -p '' python3 - " + " ".join(str(a) for a in args)
    payload = password + "\n" + script
    if extra_stdin:
        payload += "\n" + extra_stdin
    return subprocess.run(
        ["ssh", *SSH_OPTS, GUEST, remote],
        input=payload.encode(), timeout=timeout,
    )


def ssh_sudo_shell(command: str, timeout=60, extra_stdin: str = ""):
    """Run a single root shell command inside the guest (for systemctl etc.)."""
    password = env_required("CONSOLE_PASSWORD")
    payload = password + "\n" + extra_stdin
    return subprocess.run(
        ["ssh", *SSH_OPTS, GUEST, f"sudo -S -p '' {command}"],
        input=payload.encode(), timeout=timeout, capture_output=True,
    )
