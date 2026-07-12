#!/usr/bin/env python3
"""Tailscale API helpers for the final-ISO test (CI cannot ssh into the final
image, so the tailnet join is verified externally and cleaned up afterwards).

  tailscale_api.py wait-join <since-epoch>   poll until a lisa* device
                                             created after <since> appears
  tailscale_api.py cleanup <since-epoch>     delete all lisa* devices
                                             created after <since>
Env: TS_API_TOKEN. Self-skips when the token is a dummy (public repo).
"""
import base64
import datetime
import json
import os
import sys
import time
import urllib.request

API = "https://api.tailscale.com/api/v2"


def api(method: str, path: str):
    token = os.environ["TS_API_TOKEN"]
    auth = base64.b64encode(f"{token}:".encode()).decode()
    req = urllib.request.Request(
        API + path, method=method,
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return json.loads(body) if body else None


def ci_nodes(since_epoch: int) -> list:
    devices = api("GET", "/tailnet/-/devices")["devices"]
    out = []
    for d in devices:
        if not d.get("hostname", "").startswith("lisa"):
            continue
        created = datetime.datetime.fromisoformat(
            d["created"].replace("Z", "+00:00"))
        if created.timestamp() >= since_epoch:
            out.append(d)
    return out


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: tailscale_api.py wait-join|cleanup <since-epoch>")
    action, since = sys.argv[1], int(sys.argv[2])

    if not os.environ.get("TS_API_TOKEN", "").startswith("tskey-api-"):
        print("SKIP: TS_API_TOKEN is not a real API token (dummy-secret repo)",
              flush=True)
        return

    if action == "wait-join":
        print(f"waiting up to 10 min for a lisa* device created after {since}",
              flush=True)
        for _ in range(60):
            nodes = ci_nodes(since)
            if nodes:
                print("JOINED:", flush=True)
                for d in nodes:
                    print(f"  {d['id']} {d['hostname']} {d['created']}", flush=True)
                return
            time.sleep(10)
        sys.exit("FAIL: no lisa* device appeared via API")
    elif action == "cleanup":
        nodes = ci_nodes(since)
        if not nodes:
            print("no CI nodes to clean up", flush=True)
            return
        for d in nodes:
            print(f"deleting CI node {d['hostname']} ({d['id']}, created {d['created']})",
                  flush=True)
            try:
                api("DELETE", f"/device/{d['id']}")
            except Exception as e:  # cleanup is best-effort
                print(f"delete failed for {d['id']}: {e}", flush=True)
    else:
        sys.exit("usage: tailscale_api.py wait-join|cleanup <since-epoch>")


if __name__ == "__main__":
    main()
