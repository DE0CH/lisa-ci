# lisa-ci — unattended Ubuntu Server installer, built and tested by CI

Every push to `main` (or manual dispatch) builds a bootable **Ubuntu Server
26.04 autoinstall ISO** for the machine `lisa` and proves it works by actually
installing it twice in QEMU/KVM on the GitHub runner.

## What the final ISO does when booted on a machine
1. Wipes the first disk and installs Ubuntu Server 26.04 — zero keyboard input.
2. User `deyao`, hostname `lisa`, SSH key-only (keys from github.com/de0ch.keys),
   password auth disabled, timezone Asia/Hong_Kong.
3. Powers the machine off when done → **remove the USB, power back on**.
4. First boot: connects to **eduroam** Wi-Fi (WPA2-Enterprise PEAP/MSCHAPv2,
   interface auto-detected) or wired DHCP, installs Tailscale, joins the
   tailnet as `lisa`, then destroys the auth key on disk. Fully offline-capable
   install (wpasupplicant/curl debs bundled on the ISO).

## Pipeline
| Job | What it proves |
|---|---|
| `build` | ISO remaster reproducible from a pristine, checksum-verified Ubuntu ISO; secrets injected only at build time |
| `test-install` | Full unattended install + first boot in KVM; identity/SSH posture/offline-deb checks; **real tailnet join** (ephemeral key, node self-removes); **real PEAP/MSCHAPv2 handshake** against a simulated eduroam AP (mac80211_hwsim + hostapd) using the shipped Wi-Fi payload |
| `test-final` | The shipped artifact: installs, **rejects** the CI test key and password auth, and its tailnet join is confirmed via the Tailscale API; CI node deleted afterwards |

Artifacts: `lisa-final-iso` (the deliverable, 5-day retention), `lisa-test-iso`,
serial logs for debugging.

## Public code, private builds
This code runs in two repos with identical content: a **public** one whose
secrets are dummies, and a **private** mirror whose secrets are real and whose
`lisa-final-iso` artifact is the actual deliverable. The pipeline adapts to
dummy credentials at runtime: a fake Tailscale key can't join, so verification
asserts the retry-pending state instead (key kept, join service still enabled)
and the Tailscale API steps no-op — everything else (unattended install, SSH
posture, offline debs, the PEAP/MSCHAPv2 eduroam handshake) is fully exercised
either way. Real secrets belong only in the private repo: **artifacts on public
repos are downloadable by anyone**, and ISOs built from real secrets embed them.

## Required repository secrets
| Secret | Content |
|---|---|
| `TS_AUTHKEY_FINAL` | Reusable Tailscale auth key baked into the final ISO |
| `TS_AUTHKEY_TEST` | Reusable **ephemeral** auth key for CI test installs |
| `TS_API_TOKEN` | Tailscale API access token (verify + clean up final-test node; max 90-day lifetime) |
| `EDUROAM_IDENTITY` / `EDUROAM_PASSWORD` | eduroam credentials |
| `CONSOLE_PASSWORD` / `CONSOLE_PASSWORD_HASH` | console password for `deyao` (plaintext used by CI to sudo during in-guest verification; SHA-512 crypt hash baked into the seed) |

Rotation: auth keys and the API token expire (see the Tailscale admin console →
Settings → Keys). When a key expires, generate a new one, update the secret,
re-run the workflow.

## Flashing the ISO to a USB stick (Windows, elevated)
```powershell
# download the lisa-final-iso artifact, then:
powershell -File flash\flash-usb.ps1 -IsoPath lisa-final.iso -DiskNumber <N>
```
The script refuses any disk that is not USB-attached, not named Verbatim, or
larger than 64 GB; it writes the partition table last (avoids Windows
auto-mount corruption) and verifies with a full read-back SHA256.

## Cautions
- The installer wipes whatever machine you boot it on, without asking.
- The eduroam handshake is tested against a simulated AP with the real
  credentials; the institution's actual RADIUS server is the one untested hop.
- The Wi-Fi config does not pin the institution CA certificate.
