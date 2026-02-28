# Betaflight Blackbox Field Syncer

[![CI](https://github.com/proeugene/betaflight-blackbox-field-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/proeugene/betaflight-blackbox-field-sync/actions/workflows/ci.yml)

A pocket-sized device based on a **Raspberry Pi Zero W** that automatically downloads and clears your Betaflight FC's blackbox flash — while you're standing at the field, no laptop required.

Plug your FC into the Pi, wait for the LED, re-plug the FC into your quad, and fly again. Your logs are saved on the Pi's SD card and available over Wi-Fi from any phone.

---

## The Problem

FPV pilots who use internal SPI flash for blackbox logging run into a recurring frustration: the flash fills up mid-session. To clear it you normally need a laptop, Betaflight Configurator, and a USB cable. At the field, that's often not an option.

## The Solution

A Pi Zero W that lives in your field bag. It speaks Betaflight's MSP protocol over USB, streams the entire flash contents to its own SD card, verifies the copy with SHA-256, erases the FC flash, and blinks the LED when it's done. The whole thing is automatic — plug in, wait ~30 seconds, done.

All logs accumulate on the Pi's SD card across every flying session and every FC you use. When you get home (or right at the field), connect to the Pi's Wi-Fi hotspot and download any `.bbl` file from a browser.

---

## Demo: What the Pilot Does

```
1. FC flash fills up mid-session
2. Land, unplug FC from quad
3. Plug FC into Pi Zero W (USB OTG)
4. Watch LED:  fast blink → slow pulse → 3× rapid + solid = DONE
5. Plug FC back into quad, fly again
6. Later: connect phone to "BF-Blackbox" Wi-Fi → browser opens automatically
7. Tap Download → open in Blackbox Explorer
```

Total time at the field: ~30 seconds.

---

## Hardware Required

| Part | Notes |
|------|-------|
| Raspberry Pi Zero W **or** Zero 2 W | Zero 2 W recommended (faster startup) |
| microSD card, 16 GB+ | Stores the OS and all your flight logs |
| USB OTG cable | Micro-USB male (Pi OTG port) → USB-A female |
| Standard USB-A to micro-USB cable | Connects USB-A female → FC |
| USB battery bank | Powers the Pi via its PWR_IN port |

No extra hardware needed for the LED — the Pi's built-in ACT LED is used.

> **Important:** This works with **internal SPI flash** blackbox storage only (the most common setup — W25Q128, M25P16, etc.).
> FC-side SD cards cannot be read over MSP. If your FC uses an SD card for blackbox, remove that card and read it directly.

---

## Install

Flash **Raspberry Pi OS Lite (64-bit, bookworm)** to the SD card, then SSH in and run:

```bash
git clone https://github.com/proeugene/betaflight-blackbox-field-sync
cd betaflight-blackbox-field-sync
sudo bash install.sh --ssid "BF-Blackbox" --password "your-password"
```

That's it. The install script handles everything:

- Python package installed to `/opt/bbsyncer/`
- Wi-Fi hotspot configured (hostapd + dnsmasq)
- Captive portal so phones auto-open the web UI on connect
- mDNS hostname `blackboxdata.local` (avahi)
- systemd units: one-shot sync service + always-on web server
- udev rule to trigger sync automatically when an FC is plugged in

---

## Retrieving Your Logs

1. Power on the Pi Zero W
2. On your phone or laptop: connect to Wi-Fi **`BF-Blackbox`** (default password: `fpvpilot`)
3. **Your phone automatically pops up the blackbox page** — same as airport Wi-Fi captive portals
   - If that gets dismissed: open any browser and go to `http://blackboxdata.local` or `http://192.168.4.1`
4. You'll see all your sessions listed, grouped by FC
5. Tap **Download .bbl** — opens in [Betaflight Blackbox Explorer](https://github.com/betaflight/blackbox-log-viewer) on desktop, or the [Blackbox Explorer app](https://apps.apple.com/app/betaflight-blackbox-explorer) on iOS/Android

The web UI also shows Pi SD card free space, lets you delete old sessions to reclaim space, and displays live sync status while a download is in progress.

```
┌─────────────────────────────────────────────────┐
│  Betaflight Blackbox Syncer              [Idle]  │
├─────────────────────────────────────────────────┤
│  fc_BTFL_uid-12ab34cd                           │
│  ─────────────────────────────────────────────  │
│  2026-03-01 09:10  2.1 MB  Erased              │
│  [Download .bbl]  [Manifest]  [Delete from Pi]  │
│                                                  │
│  2026-02-26 16:15  1.8 MB  Erased              │
│  [Download .bbl]  [Manifest]  [Delete from Pi]  │
├─────────────────────────────────────────────────┤
│  Pi SD card: 12.3 GB used / 28.7 GB free       │
└─────────────────────────────────────────────────┘
```

---

## LED Guide

The Pi's built-in green LED tells you exactly what's happening.

| LED Pattern | What's Happening |
|-------------|-----------------|
| Fast blink — 100ms on/off | Copying flash to SD card |
| Medium blink — 250ms on/off | Verifying SHA-256 integrity |
| Slow pulse — 800ms on / 200ms off | Erasing FC flash |
| 3× rapid blink, then 2s solid, then off | **Success** — safe to unplug |
| 2× slow blink, then off | Flash was already empty — nothing to do |
| SOS pattern, repeating | Error — check logs (see below) |

---

## How Logs Are Stored

Logs accumulate on the Pi's SD card and are **never automatically deleted** by the sync process. Only the FC's flash is erased (and only after the copy is verified).

```
/mnt/bbsyncer-logs/
├── fc_BTFL_uid-12ab34cd/            ← one directory per FC, identified by UID
│   ├── 2026-02-26_143012/
│   │   ├── raw_flash.bbl            ← raw binary, open directly in blackbox-log-viewer
│   │   └── manifest.json            ← FC info, file size, SHA-256, erase status
│   ├── 2026-02-26_161500/
│   └── 2026-03-01_091000/           ← new sessions just keep accumulating
└── fc_BTFL_uid-deadbeef/            ← a different FC gets its own directory
    └── ...
```

Each `manifest.json` looks like:

```json
{
  "fc": { "variant": "BTFL", "uid": "12ab34cd...", "api_version": "1.45" },
  "file": { "name": "raw_flash.bbl", "bytes": 2097152, "sha256": "a3f1..." },
  "erase_completed": true,
  "created_utc": "2026-02-26T14:30:12+00:00"
}
```

---

## Configuration

The config file lives at `/etc/bbsyncer/bbsyncer.toml` after install. The defaults work out of the box; here are the settings you're most likely to change:

```toml
# Set to false to copy without erasing (useful for testing)
erase_after_sync = true

# Change the hotspot name and password
hotspot_ssid = "BF-Blackbox"
hotspot_password = "fpvpilot"

# Where logs are stored on the Pi
storage_path = "/mnt/bbsyncer-logs"

# How much free space to always keep on the SD card
min_free_space_mb = 200
```

---

## Troubleshooting

**LED shows SOS / error pattern**

```bash
# View the sync log for the most recent plug-in event:
journalctl -u "bbsyncer@ttyACM0" -n 50
```

**Web UI not loading**

```bash
journalctl -u bbsyncer-web -f
```

**FC not detected (no LED response)**

- Confirm your FC uses USB CDC-ACM (it shows up as `/dev/ttyACM0` on a normal PC with Configurator)
- Check that the FC's STM32 USB VID is `0x0483`: `lsusb | grep 0483`
- Make sure you're using the Pi's OTG port (the inner micro-USB, not the PWR port)

**Sync seems slow**

The Pi Zero W's single-core 1 GHz CPU and USB 2.0 are the bottleneck. A 2 MB flash typically takes 20–40 seconds. The Pi Zero **2** W is noticeably faster (~2× CPU).

**"FC uses SD card" error**

Your FC is configured to log to an SD card instead of internal flash. MSP cannot read FC-side SD cards. Set your FC blackbox device to "SPI Flash" in Configurator, or remove the FC SD card and read it directly.

---

## Manual / CLI Usage

```bash
# Sync (auto-detect port):
python -m bbsyncer

# Sync a specific port:
python -m bbsyncer --port /dev/ttyACM0

# Dry run — copy the flash but don't erase it:
python -m bbsyncer --port /dev/ttyACM0 --dry-run

# Start the web server only:
python -m bbsyncer --web

# Verbose logging:
python -m bbsyncer --port /dev/ttyACM0 --verbose
```

---

## Development

```bash
# Clone and set up:
git clone https://github.com/proeugene/betaflight-blackbox-field-sync
cd betaflight-blackbox-field-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # also builds the optional C extension

# Run tests:
pytest

# Run with coverage:
pytest --cov=bbsyncer --cov-report=term-missing

# Linting:
ruff check
ruff format --check

# Security scanning:
bandit -r bbsyncer/ -c pyproject.toml

# Full CI check locally:
ruff check && ruff format --check && pytest --cov=bbsyncer
```

The test suite runs entirely without hardware — the orchestrator tests use mocked MSP clients.

### Testing the web UI locally

The web server uses only Python stdlib (no Flask or other runtime dependencies), so you can run it directly against a folder of fake session data:

```bash
# Create a fake session
mkdir -p /tmp/bbsyncer-test/fc_BTFL_uid-deadbeef/2026-02-26_143012
cat > /tmp/bbsyncer-test/fc_BTFL_uid-deadbeef/2026-02-26_143012/manifest.json <<'EOF'
{"version":1,"created_utc":"2026-02-26T14:30:12Z","fc":{"variant":"BTFL","uid":"deadbeef12345678","api_version":"4.3","blackbox_device":3},"file":{"name":"raw_flash.bbl","bytes":10485760,"sha256":"abc123def456abc123def456abc123de"},"erase_attempted":true,"erase_completed":true}
EOF
touch /tmp/bbsyncer-test/fc_BTFL_uid-deadbeef/2026-02-26_143012/raw_flash.bbl

# Start the server on a non-privileged port
python -c "from bbsyncer.web.server import run_server; run_server(storage_path='/tmp/bbsyncer-test', port=8080)"
# Open http://localhost:8080
```

Or with Docker:

```bash
docker build -t bbsyncer-web .
docker run --rm -p 8080:8080 -v /tmp/bbsyncer-test:/data bbsyncer-web
# Open http://localhost:8080
```

---

## How It Works (Technical)

The Pi speaks **MSP (MultiWii Serial Protocol) v1** over USB CDC-ACM at 115,200 baud. The udev rule watches for the STMicroelectronics VID (`0x0483`) on a `ttyACM*` port and fires a one-shot systemd service.

The sync service runs a 10-step state machine:

1. **Wait** 3 s for USB enumeration to settle (systemd `ExecStartPre`)
2. **Identify FC** — `MSP_API_VERSION` + `MSP_FC_VARIANT` (must be `BTFL`) + `MSP_UID`
3. **Query flash** — `MSP_DATAFLASH_SUMMARY`: flags, total size, used size
4. **Check Pi storage** — must have enough free space for the flash + 200 MB headroom
5. **Prepare output** — create timestamped session directory, open `.bbl` file
6. **Stream flash** — `MSP_DATAFLASH_READ` in 16 KB chunks, writing to disk and updating a running SHA-256 hash. Requests are pipelined — the next chunk is requested before the current one is processed, hiding FC-side flash read latency.
7. **Verify** — re-read the file from disk, compare SHA-256; abort erase if mismatch
8. **Write manifest** — saved before erase so there's an audit trail even if erase fails
9. **Erase** — `MSP_DATAFLASH_ERASE`, then poll `MSP_DATAFLASH_SUMMARY` every 2 s until `used_size == 0`
10. **Signal** — LED pattern for success or error

The FC's flash is **never erased unless the SHA-256 verification passes**.

MSP framing, CRC8-DVB-S2, and the Huffman decompressor are ported directly from the [Betaflight Configurator](https://github.com/betaflight/betaflight-configurator) JavaScript source. Performance-critical CRC, frame decoding, and Huffman decompression are accelerated by an optional C extension (`bbsyncer/_native/_msp_fast.c`), with transparent fallback to pure Python.

---

## Architecture

```
bbsyncer/
├── msp/         MSP protocol: framing, CRC, Huffman, client
├── fc/          Flight controller detection and handshake
├── sync/        10-step sync orchestrator (main workflow)
├── storage/     Session directories, manifest.json, file writer
├── web/         stdlib HTTP server, captive portal, file downloads
├── led/         LED state machine (sysfs + GPIO backends)
├── util/        Disk space utilities
└── _native/     Optional C extension for CRC/framing/Huffman
```

---

## Compatibility

| | |
|---|---|
| **FC firmware** | Betaflight 4.0+ (MSP API 1.40+) |
| **Blackbox storage** | Internal SPI flash only (W25Q128, M25P16, AT25SF041, etc.) |
| **Hardware** | Raspberry Pi Zero W, Zero 2 W |
| **OS** | Raspberry Pi OS Lite, bookworm (64-bit) |
| **Python** | 3.11+ |

---

## Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repo and create a feature branch (`git checkout -b my-feature`)
2. Make your changes and add tests for new features
3. Run `ruff check && ruff format --check && pytest` before submitting
4. Open a **Pull Request** against `main`

CI runs automatically on PRs — it checks linting, runs the test matrix across Python 3.11–3.13, and performs security scanning with Bandit.

**Code style:** We use [ruff](https://docs.astral.sh/ruff/) with single quotes and a 100-character line length (configured in `pyproject.toml`).

---

## License

MIT
