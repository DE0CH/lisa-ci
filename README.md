# lisa-ci — unattended Ubuntu Server installer, built and tested by CI

Every push to `main` builds a bootable **Ubuntu Server 26.04 autoinstall ISO**
for the machine `lisa` and proves it works by installing it twice in QEMU/KVM
on the GitHub runner. The `lisa-final-iso` artifact is the deliverable.

## What the release ISO does when booted on a machine
1. Wipes the first disk and installs Ubuntu Server 26.04 — zero keyboard input.
2. User `deyao`, hostname `lisa`, timezone Asia/Hong_Kong. **SSH-key-only**
   (keys from github.com/de0ch.keys): password auth disabled, the account
   password is random and discarded at build time, sudo is passwordless
   (cloud-image convention).
3. Powers the machine off when done → **remove the USB, power back on**.
4. First boot: connects to **eduroam** Wi-Fi (WPA2-Enterprise PEAP/MSCHAPv2,
   interface auto-detected) or wired DHCP, installs Tailscale, joins the
   tailnet, then destroys the auth key on disk. The install is fully
   offline-capable (wpasupplicant/curl debs bundled on the ISO).

## Secrets (four)
| Secret | Used by | Public repo | Private repo |
|---|---|---|---|
| `TS_AUTHKEY_RELEASE` | baked into the **release** ISO | dummy | real (reusable) |
| `EDUROAM_USERNAME` | baked into the **release** ISO | dummy | real |
| `EDUROAM_PASSWORD` | baked into the **release** ISO | dummy | real |
| `TS_AUTHKEY_SECRET` | **runtime-injected** in the manual connectivity test; never in any artifact | real (ephemeral) | real (ephemeral) |

The test ISO involves no secrets at all: it is built with a dummy tailscale
key and **code-generated** dummy eduroam credentials; the eduroam test reads
those back out of the shipped script inside the guest.

## Workflows
**`build-and-test`** (push) — never touches the tailnet:
| Job | What it proves |
|---|---|
| `build` | ISO remaster reproducible from a pristine, checksum-verified Ubuntu ISO |
| `test-install` | Full unattended install + first boot in KVM; identity, SSH posture, NOPASSWD sudo, offline debs; join service in correct retry-pending state; **real PEAP/MSCHAPv2 handshake** against a simulated eduroam AP (mac80211_hwsim + hostapd) using the shipped Wi-Fi payload |
| `test-final` | The release artifact installs and **rejects** everything but the de0ch.keys identity; booted with guest networking **restricted** so its baked key cannot fire from CI |

**`ts-connectivity`** (manual dispatch) — the one test that touches the
tailnet: installs the test ISO, injects `TS_AUTHKEY_SECRET` over SSH, verifies
the in-guest join, and holds the VM online (`hold_seconds` input) so the
operator can confirm the node's appearance on the tailnet from outside. The
workflow deliberately has no tailnet-side view; confirmation is the operator's
job. The key is ephemeral, so the node self-removes after the VM stops.

## Public code, private builds
Two repos, identical code. The public one carries dummy baked-credential
secrets, so all of its artifacts are harmless; the private mirror carries the
real ones and produces the actual release. **Artifacts on public repos are
downloadable by anyone** — never set real baked credentials there. (The
runtime-injected `TS_AUTHKEY_SECRET` is safe on both: it never enters an
artifact.)

## Using the ISO
Download the `lisa-final-iso` artifact and write it to a USB stick with any
raw imaging tool (`dd`, Rufus in dd mode, balenaEtcher). Flashing is out of
scope for this repo — the deliverable is the verified ISO.

## Cautions
- The installer wipes whatever machine you boot it on, without asking.
- The eduroam handshake is tested against a simulated AP; the institution's
  actual RADIUS server is the one untested hop. The Wi-Fi config does not pin
  the institution CA certificate.
- Auth keys expire (Tailscale admin console → Settings → Keys): rotate the
  secret and re-run when they do.
