# Changelog

All notable changes to LogFalcon are documented here.

## [v0.4.0] — 2025-03

### Added
- **Hard block for too-old firmware**: Betaflight older than 4.0 (MSP API < 1.41) and iNav older than 2.6 (API < 1.40) are rejected at identification time with a clear, actionable error message. This prevents log corruption — `MSP_DATAFLASH_READ` changed wire format in BF 4.0.
- **Soft warning for untested-new firmware**: firmware above the max tested version (BF 4.6 / iNav 7.0) shows an amber banner in the dashboard. Sync proceeds — the warning is informational.
- **FC identity in dashboard**: after MSP handshake completes, the dashboard shows `⚡ FC: Betaflight 4.5.0 (API 1.46)`. Clears automatically at the start of each new sync cycle.

---

## [v0.3.9] — 2025-02

### Fixed
- **Wi-Fi hotspot not visible on first boot** — three root causes diagnosed via image inspection:
  1. `wpa_supplicant` was enabled by default in Bookworm Lite, stealing `wlan0` from `hostapd`; symlink now removed directly in pi-gen chroot
  2. `openssl passwd -6 -stdin` outputs nothing on Linux — changed to `openssl passwd -6 'logfalcon'` (portable direct argument)
  3. `dnsmasq` started before `wlan0` was configured — added systemd drop-in override (`After=sys-subsystem-net-devices-wlan0.device`, `Restart=on-failure`) for both `dnsmasq` and `hostapd`

### Added
- `scripts/inspect-image.sh` — mounts any `.img` / `.img.xz` via Parallels VM or Docker and audits hotspot config, service states, and binary presence

---

## [v0.3.8] — 2025-02

### Changed
- Wi-Fi SSID default renamed from `BF-Blackbox` → `LogFalcon` across Go code, config templates, pi-gen, install scripts, and all docs. Existing installs are unaffected (SSID is read from the deployed config file).

---

## [v0.3.7] — 2025-01

### Fixed
- Binary artifacts now correctly attached to GitHub Releases (was broken — `go-ci.yml` never triggered on tag pushes)
- `golangci-lint` pinned to `v1.64.8` (was `latest`)
- `xz -9e` → `xz -9` in image build (saves ~5–10 min per release)

### Added
- Real-time sync progress documented in README and guide (state badge colours, progress bar, speed, ETA)

---

## [v0.3.6] — 2025-01

### Added
- **Real-time sync progress**: web dashboard now shows `Syncing flash… 45%  (2.1 / 4.0 MB)  · 1.2 MB/s · ~18s remaining` with a live progress bar
- **SSH access documented**: credentials, `passwd`, SSH connection strings added to README and guide

### Fixed
- **Headless boot on Bookworm** (`userconfig.service` wizard): belt-and-suspenders fix — pi-gen sets `FIRST_USER_PASS`, `userconf.txt` written to boot partition, `userconfig.service` disabled in chroot

---

## [v0.3.5] — 2024-12

### Added
- `scripts/install.sh` — one-command installer for existing Raspberry Pi OS installs (`curl ... | sudo bash`)
- `scripts/uninstall.sh` — clean one-command uninstaller

---

## [v0.3.4] — 2024-12

### Performance
- **MSP v2 flash reads**: 16-bit length field → ~4 KB frames (was 255 B) — ~16× per-frame throughput
- **Baud rate 921,600**: 8× raw UART throughput
- **Estimated sync times (16 MB flash)**: UART ~2.5 min (was ~20 min), USB ~30–60 sec (was ~5–9 min)

---

## [v0.3.1] — 2024-11

### Changed
- Removed all legacy Python code; Go rewrite is now the sole implementation
- Multi-stage Dockerfile (golang:1.22-alpine → alpine:3.20)
- pi-gen no longer installs Python — copies pre-built Go binary instead
- All packages migrated from `log.Printf` to `slog`

### Added
- `docs/guide.html` — 9-section field pilot guide

---

## [v0.3.0] — 2024-11

### Added
- Complete rewrite from Python to Go
  - ~6 MB single static binary (was ~250 MB Python venv)
  - ~10 ms cold start (was 500 ms–2 s)
  - ~5–10 MB idle memory (was 45–55 MB)
  - Zero runtime dependencies on Pi
- Race-detector tested: all tests pass with `go test -race`
