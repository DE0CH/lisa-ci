#!/usr/bin/env python3
"""Refuse to bake real credentials into a public repo's artifacts.

Artifacts on public repos are downloadable by anyone, and the seed render
bakes TS_AUTHKEY_FINAL and the eduroam credentials into the ISOs. On a public
repo those secrets must therefore be dummies:

- TS_AUTHKEY_FINAL must NOT look like a real key (no "tskey-" prefix)
- EDUROAM_PASSWORD must contain the substring "dummy" (documented convention)

TS_AUTHKEY_TEST is exempt: it is injected over SSH at test time and never
enters an artifact. Private repos skip all checks.
"""
import os
import sys


def main() -> None:
    visibility = os.environ.get("REPO_VISIBILITY", "")
    print(f"repository visibility: {visibility or 'unknown'}", flush=True)
    if visibility != "public":
        print("private/internal repo: real baked credentials are allowed", flush=True)
        return

    problems = []
    if os.environ.get("TS_AUTHKEY_FINAL", "").startswith("tskey-"):
        problems.append("TS_AUTHKEY_FINAL looks like a REAL tailscale key")
    if "dummy" not in os.environ.get("EDUROAM_PASSWORD", "").lower():
        problems.append('EDUROAM_PASSWORD does not contain "dummy" '
                        "(public repos must use dummy eduroam credentials)")
    if problems:
        for p in problems:
            print(f"REFUSING TO BUILD: {p}", flush=True)
        print("This repo is PUBLIC: its artifacts are downloadable by anyone. "
              "Move real secrets to the private mirror.", flush=True)
        sys.exit(1)
    print("public repo with dummy baked credentials: OK", flush=True)


if __name__ == "__main__":
    main()
